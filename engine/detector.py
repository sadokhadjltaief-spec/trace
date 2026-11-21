"""Explanation detector: (question, chosen option, explanation) -> distribution over LABELS.

LABELS = M0, M1..M4, other.  MAP rows map as: our 4 MAP labels -> M1..M4; any other MAP misconception ->
"other"; no misconception (Correct / Neither) -> M0.  bayes.observe_explanation folds "other" into M0
(engine M0 = "none of M1..M4").

1. TF-IDF (word 1-2 grams on question/answer tokens + explanation, char 3-5 grams on the explanation)
   + logistic regression, trained on MAP.
2. LLM few-shot: the 8 most similar labelled MAP explanations for the same question; the LLM returns a RANKING
   of labels (JSON). Code turns the ranking into a distribution with fixed weights (config detector.rank_weights);
   the LLM never outputs probabilities.
3. Combined = mean of 1 and 2. Non-English input (Arabic, French, Tunisian Darija in Arabic or Latin script)
   is detected and translated to English with the LLM (cached); both texts are kept.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from engine import ROOT, llm, mathcheck as mc
from engine.config import cfg

LABELS = ["M0", "M1", "M2", "M3", "M4", "other"]
MAP_TO_M = {"Adding_across": "M1", "Duplication": "M2", "Positive": "M3", "Additive": "M4"}
MODEL_PATH = ROOT / ".cache" / "detector_tfidf.joblib"

DESCR = {
    "M0": "No misconception: correct reasoning, or a slip/unclear reasoning with no identifiable misconception.",
    "M1": "Adds numerators and adds denominators when adding fractions (a/b + c/d = (a+c)/(b+d)).",
    "M2": "Multiplies both numerator and denominator by the whole number (k x a/b = ka/kb).",
    "M3": "Thinks 'two negatives make a positive' always applies, so the answer must be positive (e.g. -8 - -5 = 3 or 13).",
    "M4": "Makes equivalent fractions by adding the same number to top and bottom instead of multiplying.",
    "other": "A different, identifiable misconception that is not M1-M4.",
}


# ---------------------------------------------------------------- data
def map_label(row) -> str:
    m = row["Misconception"]
    if isinstance(m, str) and m:
        return MAP_TO_M.get(m, "other")
    return "M0"


def load_map() -> pd.DataFrame:
    df = pd.read_csv(ROOT / "data" / "raw" / "map" / "train.csv", encoding="utf-8")
    df["label"] = df.apply(map_label, axis=1)
    right = (df[df.Category.str.startswith("True")].groupby("QuestionId").MC_Answer
             .agg(lambda s: s.value_counts().idxmax()))
    df["is_correct"] = df.apply(lambda r: r.MC_Answer == right[r.QuestionId], axis=1)
    df["StudentExplanation"] = df.StudentExplanation.fillna("").astype(str)
    return df


def _answer_token(ans: str) -> str:
    v = mc.value(ans)
    s = str(v) if v is not None else mc.latex_to_plain(ans)
    return re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_") or "x"


def features(qid, answer: str, correct: bool, explanation: str) -> dict:
    meta = f"__q{qid if qid is not None else 'new'} __a{_answer_token(answer)} __{'right' if correct else 'wrong'}"
    return {"meta": meta + " " + explanation, "expl": explanation}


def frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["meta", "expl"])


def map_frame(df: pd.DataFrame) -> pd.DataFrame:
    return frame([features(r.QuestionId, r.MC_Answer, r.is_correct, r.StudentExplanation)
                  for r in df.itertuples()])


# ---------------------------------------------------------------- TF-IDF model
def make_tfidf() -> Pipeline:
    ct = ColumnTransformer([
        ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, lowercase=True), "meta"),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, sublinear_tf=True,
                                 max_features=60000), "expl"),
    ])
    return Pipeline([("x", ct), ("lr", LogisticRegression(C=4.0, max_iter=3000))])


def train_tfidf(df: pd.DataFrame) -> Pipeline:
    m = make_tfidf()
    m.fit(map_frame(df), df["label"])
    return m


def proba(model: Pipeline, X: pd.DataFrame) -> np.ndarray:
    """Probabilities in LABELS order (columns for labels unseen in training are 0)."""
    P = model.predict_proba(X)
    out = np.zeros((len(X), len(LABELS)))
    for j, c in enumerate(model.classes_):
        out[:, LABELS.index(c)] = P[:, j]
    return out


_live_model: Pipeline | None = None


def live_model() -> Pipeline:
    """TF-IDF model trained on ALL labelled MAP rows (the eval uses its own 80/20 split)."""
    global _live_model
    if _live_model is None:
        if MODEL_PATH.exists():
            _live_model = joblib.load(MODEL_PATH)
        else:
            _live_model = train_tfidf(load_map())
            MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(_live_model, MODEL_PATH)
    return _live_model


# ---------------------------------------------------------------- LLM variants
SYS = """You classify a school student's written explanation of a multiple-choice maths answer.
Labels:
{labels}
Rank the labels from most to least likely for EACH item. Judge the reasoning, not only the answer:
a correct answer can come with flawed reasoning, and a wrong answer can be a slip (M0).
Return JSON only: {{"items": [{{"id": "<item id>", "ranking": ["<best>", "<2nd>", "<3rd>"]}}, ...]}}"""


def _labels_block() -> str:
    return "\n".join(f"- {k}: {v}" for k, v in DESCR.items())


def _item_block(item: dict, examples: list[dict] | None) -> str:
    s = (f"[item {item['id']}]\nQuestion: {mc.latex_to_plain(item['question'])}\n"
         f"Student's answer: {mc.latex_to_plain(item['answer'])} ({'correct' if item['correct'] else 'incorrect'})\n"
         f"Explanation: {item['explanation']}\n")
    if examples:
        s += "Labelled examples from other students on the same question:\n" + "\n".join(
            f"  - answer {mc.latex_to_plain(e['answer'])}: \"{e['explanation']}\" -> {e['label']}" for e in examples)
    return s


def rank_to_dist(ranking: list[str]) -> np.ndarray:
    w = cfg().get("detector", {}).get("rank_weights", [0.7, 0.2, 0.1])
    eps = cfg().get("detector", {}).get("rank_floor", 0.01)
    d = np.full(len(LABELS), eps)
    seen = []
    for r in ranking:
        if r in LABELS and r not in seen:
            seen.append(r)
    for i, r in enumerate(seen[:len(w)]):
        d[LABELS.index(r)] += w[i]
    return d / d.sum()


def llm_rank(items: list[dict], examples: dict[str, list[dict]] | None, *, model: str | None,
             purpose: str) -> dict[str, list[str]]:
    """One LLM call ranks several items (batched to fit the free-tier request budget)."""
    sysmsg = SYS.format(labels=_labels_block())
    user = "\n".join(_item_block(it, (examples or {}).get(it["id"])) for it in items)
    data = llm.ask_json(sysmsg, user, purpose=purpose, model=model,
                        max_tokens=min(4096, 400 + 120 * len(items)))
    out = {}
    for it in (data or {}).get("items", []):
        if isinstance(it, dict) and "id" in it:
            out[str(it["id"])] = [str(x) for x in it.get("ranking", [])]
    return out


# ---------------------------------------------------------------- example retrieval (few-shot)
@dataclass
class ExampleIndex:
    df: pd.DataFrame
    vec: TfidfVectorizer
    X: object

    @classmethod
    def build(cls, df: pd.DataFrame) -> "ExampleIndex":
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True)
        X = vec.fit_transform(df.StudentExplanation)
        return cls(df.reset_index(drop=True), vec, X)

    def nearest(self, qid, explanation: str, k: int = 8) -> list[dict]:
        mask = (self.df.QuestionId == qid).to_numpy() if qid is not None else np.ones(len(self.df), bool)
        if not mask.any():
            return []
        idx = np.flatnonzero(mask)
        sims = (self.X[idx] @ self.vec.transform([explanation]).T).toarray().ravel()
        best = idx[np.argsort(-sims)[:k]]
        return [{"answer": self.df.MC_Answer[i], "explanation": self.df.StudentExplanation[i][:200],
                 "label": self.df.label[i]} for i in best]


_live_index: ExampleIndex | None = None


def live_index() -> ExampleIndex:
    global _live_index
    if _live_index is None:
        _live_index = ExampleIndex.build(load_map())
    return _live_index


# ---------------------------------------------------------------- language
_AR = re.compile(r"[؀-ۿ]")
_DARIJA_LATIN = re.compile(r"\b\w*[a-z][379]\w*\b|\b[379][a-z]\w*\b", re.I)
_DARIJA_WORDS = {"3la", "chnowa", "chnua", "kifech", "5ater", "khater", "barcha", "ya3ni", "mta3", "bech", "nja3",
                 "ama", "fama", "mouch", "mich", "9ad", "chwaya", "sa7a", "3andi", "na3ref", "7aja", "ki", "w"}
_FR_WORDS = {"le", "la", "les", "des", "est", "et", "parce", "que", "je", "il", "on", "car", "une", "un", "du",
             "pour", "fois", "plus", "moins", "donc", "c'est", "j'ai", "ai", "fait", "dénominateur", "numérateur"}
_EN_WORDS = {"the", "is", "and", "because", "i", "it", "you", "times", "add", "so", "of", "to", "then"}


def detect_language(text: str) -> str:
    """Deterministic: 'ar', 'darija' (Arabizi: Latin script with 3/7/9 as letters), 'fr' or 'en'."""
    if _AR.search(text):
        return "ar"  # Arabic-script Darija and MSA both go through translation as 'ar'
    words = re.findall(r"[\w']+", text.lower())
    if not words:
        return "en"
    darija = sum(w in _DARIJA_WORDS for w in words) + len(_DARIJA_LATIN.findall(text))
    fr = sum(w in _FR_WORDS for w in words) + len(re.findall(r"[éèêàçùâîô]", text.lower()))
    en = sum(w in _EN_WORDS for w in words)
    if darija >= 2 and darija >= fr and darija >= en:
        return "darija"
    if fr > en:
        return "fr"
    return "en"


TRANSLATE_SYS = """Translate a school student's short maths explanation into plain English.
The input may be French, Modern Standard Arabic, or Tunisian Darija (Arabic script or Latin script where
digits stand for letters: 3 = ع, 7 = ح, 9 = ق, 5 = خ). Keep the maths exactly as written (numbers, operations,
mistakes). Do not correct the student's reasoning. Return JSON: {"english": "..."}"""


def to_english(text: str, lang: str | None = None, *, model: str | None = None) -> tuple[str, str]:
    lang = lang or detect_language(text)
    if lang == "en" or not text.strip():
        return text, lang
    d = llm.ask_json(TRANSLATE_SYS, f"Language hint: {lang}\nText: {text}", purpose="translate_to_en", model=model)
    return str((d or {}).get("english", "")).strip() or text, lang


# ---------------------------------------------------------------- live entry point
def detect(question: dict, option: str, explanation: str, *, use_llm: bool = True) -> dict:
    """question = a bank question dict (needs text/options/correct, optional map_question_id)."""
    english, lang = explanation, "en"
    notes = []
    if use_llm:
        try:
            english, lang = to_english(explanation)
        except Exception as e:  # noqa: BLE001 - fall back to the raw text
            lang = detect_language(explanation)
            notes.append(f"translation unavailable ({type(e).__name__})")
    else:
        lang = detect_language(explanation)
    qid = question.get("map_question_id")
    correct = option == question["correct"]
    answer = question["options"][option]
    X = frame([features(qid, answer, correct, english)])
    p_tfidf = proba(live_model(), X)[0]
    dist, comps = p_tfidf, {"tfidf": dict(zip(LABELS, map(float, p_tfidf)))}
    if use_llm:
        try:
            ex = {"x": live_index().nearest(qid, english)} if qid is not None else None
            rk = llm_rank([{"id": "x", "question": question["text"], "answer": answer, "correct": correct,
                            "explanation": english}], ex, model=None, purpose="detector_fewshot").get("x", [])
            if rk:
                p_llm = rank_to_dist(rk)
                comps["llm_fewshot"] = dict(zip(LABELS, map(float, p_llm)))
                dist = (p_tfidf + p_llm) / 2
        except Exception as e:  # noqa: BLE001
            notes.append(f"LLM detector unavailable ({type(e).__name__}); TF-IDF only")
    return {"dist": dict(zip(LABELS, map(float, dist))), "lang": lang, "original": explanation,
            "english": english, "components": comps, "notes": notes,
            "method": "combined" if "llm_fewshot" in comps else "tfidf"}


def save_json(obj, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
