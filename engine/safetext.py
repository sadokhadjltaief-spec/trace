"""The only way the engine builds text for the frontend (contract.SafeText).

- origin "template" / "verified_bank": human-written or human-approved text. leak/congruency/math checks are
  not applicable (no generated content); the style linter always runs.
- origin "llm": all four checks must have run (engine/guards.py) and none failed.
"""
from __future__ import annotations

from engine import style
from engine.contract import Check, SafeText


def static(text: str, *, origin: str = "template", lang: str = "en", style_kwargs: dict | None = None,
           fallback_used: bool = False) -> SafeText:
    viol = style.lint(text, **(style_kwargs or {}))
    checks = [Check(name=n, status="not_applicable", detail=f"{origin} text") for n in ("leak", "congruency", "math")]
    checks.append(Check(name="style", status="fail" if viol else "pass", detail="; ".join(viol)))
    return SafeText(text=text, lang=lang, origin=origin, checks=checks, shown_allowed=not viol,
                    fallback_used=fallback_used)


def from_guards(text: str, checks: list[Check], *, lang: str = "en", fallback_used: bool = False) -> SafeText:
    names = {c.name for c in checks}
    ok = {"leak", "congruency", "math", "style"} <= names and not any(c.status == "fail" for c in checks)
    return SafeText(text=text, lang=lang, origin="llm", checks=checks, shown_allowed=ok, fallback_used=fallback_used)
