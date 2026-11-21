"""Support profiles (engine/profiles.yaml) + deterministic style linter (CLAUDE.md section 11).

The profile adapts communication style only, never the diagnosis. The linter checks every displayable text
(tutor messages, templates, Study Studio outputs): words per sentence, question marks, idioms (EN/FR/AR),
praise words, emoji, ALL-CAPS, exclamation marks. The idiom and praise lists are our own short lists, not an
exhaustive resource.
"""
from __future__ import annotations

import functools
import re

import yaml

from engine import ROOT

_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]")
_SENT = re.compile(r"(?<=[.!?؟])\s+|\n+")

IDIOMS = {
    "en": ["piece of cake", "a breeze", "no-brainer", "no brainer", "hit the nail", "on the right track", "ballpark",
           "think outside the box", "you've got this", "you got this", "nail it", "in a nutshell", "easy peasy",
           "under your belt", "get the hang", "walk in the park", "spot on", "light bulb", "tricky little",
           "sneaky", "a snap", "hang in there", "the bottom line", "rule of thumb", "food for thought"],
    "fr": ["c'est du gâteau", "les doigts dans le nez", "simple comme bonjour", "la main à la pâte",
           "sur la bonne voie", "en un clin d'œil", "en un clin d'oeil", "un jeu d'enfant", "pas sorcier",
           "la tête dans les nuages", "mettre le doigt sur", "tomber dans le panneau", "petit piège"],
    "ar": ["على الطاير", "سهل كشرب الماء", "عصفورين بحجر", "في لمح البصر", "على الطريق الصحيح", "بسيطة جدًا"],
}
PRAISE = {
    "en": ["great job", "awesome", "amazing", "fantastic", "brilliant", "well done", "excellent", "super",
           "bravo", "good job", "perfect", "wonderful"],
    "fr": ["bravo", "super", "génial", "excellent", "magnifique", "formidable", "parfait", "bien joué"],
    "ar": ["ممتاز", "رائع", "أحسنت", "مذهل", "عظيم", "برافو"],
}


@functools.lru_cache(maxsize=1)
def _profiles() -> dict:
    return yaml.safe_load((ROOT / "engine" / "profiles.yaml").read_text(encoding="utf-8"))


def defaults() -> dict:
    return dict(_profiles()["toggles"])


def preset(name: str) -> dict:
    return {**defaults(), **_profiles()["presets"][name]}


def resolve(profile: dict | None) -> dict:
    """Merge a profile dict over the defaults. {'preset': 'clear_structured', ...} applies the preset first."""
    p = dict(profile or {})
    base = preset(p.pop("preset")) if p.get("preset") else defaults()
    return {**base, **{k: v for k, v in p.items() if k in base}}


def lint_kwargs(profile: dict | None, lang: str = "en") -> dict:
    p = resolve(profile)
    return {"max_words_per_sentence": int(p["max_words_per_sentence"]), "neutral": True,
            "max_questions": 1 if p["one_question_per_message"] else 2, "lang": lang,
            "literal": bool(p["literal_language"]), "no_praise": bool(p["neutral_feedback"])}


def prompt_rules(profile: dict | None) -> str:
    """Extra rules for the LLM prompt (empty for the default profile, so default prompts stay identical)."""
    p = resolve(profile)
    rules = []
    if p["literal_language"]:
        rules.append("Use literal, concrete words only: no idioms, metaphors, sarcasm or rhetorical questions.")
    if p["one_question_per_message"]:
        rules.append("Ask at most ONE question in the whole message.")
    if p["neutral_feedback"]:
        rules.append("Neutral, specific feedback: no praise words, no exclamation marks.")
    if p["max_words_per_sentence"] < 25:
        rules.append(f"Short sentences: at most {p['max_words_per_sentence']} words each.")
    if p.get("example_theme"):
        rules.append(f"If you give an example, set it in this context: {str(p['example_theme'])[:40]}. "
                     "Never change the numbers or the maths because of the context.")
    return "".join("\n- " + r for r in rules)


def _contains(text: str, phrase: str) -> bool:
    if re.search(r"[؀-ۿ]", phrase):  # Arabic: substring match (attached prefixes like و / ب)
        return phrase in text
    return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text, re.I) is not None


def lint(text: str, *, max_words_per_sentence: int = 25, neutral: bool = True, max_questions: int | None = None,
         lang: str = "en", literal: bool = False, no_praise: bool = False) -> list[str]:
    """Return a list of violations (empty = pass)."""
    v = []
    for s in _SENT.split(text.strip()):
        n = len(re.findall(r"\S+", s))
        if n > max_words_per_sentence:
            v.append(f"sentence has {n} words (max {max_words_per_sentence})")
    if _EMOJI.search(text):
        v.append("contains emoji")
    if re.search(r"\b[A-Z]{4,}\b", re.sub(r"\\\(.*?\\\)", "", text)):
        v.append("contains ALL-CAPS word")
    if neutral and "!" in text:
        v.append("exclamation mark in neutral mode")
    if max_questions is not None and text.count("?") + text.count("؟") > max_questions:
        v.append(f"more than {max_questions} question mark(s)")
    langs = [lang] if lang in IDIOMS else list(IDIOMS)
    if literal:
        hits = [i for lg in langs for i in IDIOMS[lg] if _contains(text, i)]
        if hits:
            v.append(f"idiom (literal language): {hits}")
    if no_praise:
        hits = [w for lg in langs for w in PRAISE[lg] if _contains(text, w)]
        if hits:
            v.append(f"praise word (neutral feedback): {hits}")
    return v
