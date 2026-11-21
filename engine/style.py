"""Deterministic style linter. Base rules now; support-profile toggles are added in step 10."""
from __future__ import annotations

import re

_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]")
_SENT = re.compile(r"(?<=[.!?؟])\s+")


def lint(text: str, *, max_words_per_sentence: int = 25, neutral: bool = True,
         max_questions: int | None = None) -> list[str]:
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
    return v
