"""Bayesian misconception diagnosis. All diagnosis numbers in TRACE come from here (never from the LLM).

Hypotheses H = [M0, M1..M4]  (M0 = none of M1..M4).
Likelihood P(option | question, h):
  defaults  : option mapped to h -> p_hit (split evenly if several options map to h);
              correct & h=M0 -> p_correct_m0; correct & h!=M0 -> p_correct_despite;
              remaining mass spread evenly over the other options; eps floor; normalise per (q, h).
  MAP data  : where MAP has rows for (q, h), use add-one-smoothed MAP answer frequencies instead
              (h = the question's MAP label, and M0 = rows with no misconception label).
Evidence    : answers (+ confidence tap), explanation-detector distributions (tempered by tau),
              and any other source via update_lik() (games, simulations, flashcard lapses).
Next question = argmax expected information gain; stop at max P >= threshold or after max_questions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from engine import ROOT
from engine.config import cfg

H = ["M0", "M1", "M2", "M3", "M4"]


def params(**override) -> dict:
    p = dict(cfg()["bayes"])
    p.update({k: v for k, v in override.items() if v is not None})
    return p


def entropy(p: np.ndarray) -> float:
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


# ------------------------------------------------------------------ likelihood tables
def default_row(q: dict, h: str, p: dict) -> dict[str, float]:
    opts = list(q["options"])
    om = q.get("option_misconception", {})
    row: dict[str, float] = {}
    hits = [a for a in opts if om.get(a) == h and a != q["correct"]]
    for a in hits:
        row[a] = p["p_hit"] / len(hits)
    row[q["correct"]] = p["p_correct_m0"] if h == "M0" else p["p_correct_despite"]
    rest = [a for a in opts if a not in row]
    left = max(0.0, 1.0 - sum(row.values()))
    for a in rest:
        row[a] = left / len(rest)
    return _normalise({a: max(row[a], p["eps"]) for a in opts})


def data_row(q: dict, h: str, p: dict) -> dict[str, float] | None:
    counts = (q.get("map_label_answer_counts") or {}).get(h)
    if not counts or not p.get("use_map_data", True):
        return None
    k = p.get("smoothing", 1)
    return _normalise({a: counts.get(a, 0) + k for a in q["options"]})


def _normalise(row: dict[str, float]) -> dict[str, float]:
    s = sum(row.values())
    return {a: v / s for a, v in row.items()}


@dataclass
class Table:
    """L[q][h][a] for a set of questions, plus which rows came from data."""
    questions: dict[str, dict]
    L: dict[str, dict[str, dict[str, float]]]
    source: dict[str, dict[str, str]]  # q -> h -> "map_data" | "default"

    def vec(self, qid: str, option: str) -> np.ndarray:
        return np.array([self.L[qid][h][option] for h in H])

    def matrix(self, qid: str) -> tuple[list[str], np.ndarray]:
        opts = list(self.questions[qid]["options"])
        return opts, np.array([[self.L[qid][h][a] for a in opts] for h in H])  # [h, a]

    def data_usage(self) -> dict:
        return {q: {h: s for h, s in hs.items()} for q, hs in self.source.items()}


def build_table(questions: list[dict], **override) -> Table:
    p = params(**override)
    L, src = {}, {}
    for q in questions:
        L[q["id"]], src[q["id"]] = {}, {}
        for h in H:
            r = data_row(q, h, p)
            src[q["id"]][h] = "map_data" if r else "default"
            L[q["id"]][h] = r or default_row(q, h, p)
    return Table({q["id"]: q for q in questions}, L, src)


# ------------------------------------------------------------------ the posterior
@dataclass
class Event:
    source: str
    detail: dict
    lik: list[float]
    posterior: list[float]


@dataclass
class Diagnoser:
    table: Table
    p: dict = field(default_factory=params)
    logp: np.ndarray = field(default=None)
    asked: list[str] = field(default_factory=list)
    history: list[Event] = field(default_factory=list)
    fragile: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.logp is None:
            self.logp = np.log(load_prior())

    # --- state
    @property
    def posterior(self) -> np.ndarray:
        x = self.logp - self.logp.max()
        e = np.exp(x)
        return e / e.sum()

    def as_dict(self) -> dict[str, float]:
        return dict(zip(H, map(float, self.posterior)))

    def top(self) -> tuple[str, float]:
        post = self.posterior
        i = int(post.argmax())
        return H[i], float(post[i])

    def done(self) -> bool:
        return self.top()[1] >= self.p["stop_threshold"] or len(self.asked) >= self.p["max_questions"]

    # --- generic evidence API (games, sims, flashcards use this too)
    def update_lik(self, lik, source: str, detail: dict | None = None) -> None:
        lik = np.asarray([lik[h] for h in H] if isinstance(lik, dict) else lik, dtype=float)
        lik = np.maximum(lik, 1e-12)
        self.logp = self.logp + np.log(lik)
        self.logp -= self.logp.max()
        self.history.append(Event(source, detail or {}, lik.tolist(), self.posterior.tolist()))

    # --- answers
    def answer_lik(self, qid: str, option: str, confidence: str | None = None) -> tuple[np.ndarray, str]:
        q = self.table.questions[qid]
        lik = self.table.vec(qid, option)
        correct = option == q["correct"]
        note = ""
        if confidence == "sure" and not correct:
            k = self.p["k_conf"]
            lik = lik * np.array([1 / k] + [k] * (len(H) - 1))
            note = "wrong+sure"
        elif confidence == "unsure" and not correct:
            lik = lik ** self.p["unsure_power"]
            note = "wrong+unsure"
        elif confidence == "unsure" and correct:
            lik = lik ** self.p.get("fragile_power", 0.6)
            note = "fragile"
        return lik, note

    def observe_answer(self, qid: str, option: str, confidence: str | None = None) -> None:
        lik, note = self.answer_lik(qid, option, confidence)
        if note == "fragile":
            self.fragile.append(qid)
        if qid not in self.asked:
            self.asked.append(qid)
        self.update_lik(lik, "answer", {"question": qid, "option": option, "confidence": confidence,
                                        "correct": option == self.table.questions[qid]["correct"], "note": note})

    # --- explanation detector
    def observe_explanation(self, dist: dict[str, float], detail: dict | None = None) -> None:
        tau = self.p["tau"]
        lik = np.array([max(dist.get(h, 0.0), self.p["eps"]) for h in H]) ** tau
        self.update_lik(lik, "explanation", detail or {"dist": dist})

    # --- question selection
    def expected_ig(self, qid: str) -> float:
        post = self.posterior
        _, M = self.table.matrix(qid)           # [h, a]
        pa = post @ M                           # P(a | q)
        h_now = entropy(post)
        exp_h = 0.0
        for j, pa_j in enumerate(pa):
            if pa_j <= 0:
                continue
            post_a = post * M[:, j]
            post_a /= post_a.sum()
            exp_h += pa_j * entropy(post_a)
        return h_now - exp_h

    def rank_questions(self, candidates: list[str] | None = None) -> list[tuple[str, float]]:
        cands = [q for q in (candidates or list(self.table.questions)) if q not in self.asked]
        return sorted(((q, self.expected_ig(q)) for q in cands), key=lambda t: -t[1])

    def next_question(self, candidates: list[str] | None = None) -> dict:
        ranked = self.rank_questions(candidates)
        if not ranked or self.done():
            return {"question": None, "ig_bits": 0.0, "alternatives": [], "stop": True}
        return {"question": ranked[0][0], "ig_bits": ranked[0][1],
                "alternatives": [{"question": q, "ig_bits": ig} for q, ig in ranked[1:3]], "stop": False}


def load_prior() -> np.ndarray:
    p = ROOT / "data" / "bank" / "prior.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        v = np.array([float(d[h]) for h in H])
        return v / v.sum()
    return np.full(len(H), 1 / len(H))


def load_bank(path: Path | None = None, verified_only: bool = False, allow_blocked: bool = False) -> dict:
    b = json.loads((path or ROOT / "data" / "bank" / "bank.json").read_text(encoding="utf-8"))
    qs = b["questions"]
    if not allow_blocked:
        qs = [q for q in qs if not q.get("blocked_by")]
    if verified_only:
        qs = [q for q in qs if q.get("verified")]
    b["questions"] = qs
    return b
