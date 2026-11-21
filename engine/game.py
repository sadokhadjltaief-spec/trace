"""Game "Chasse aux erreurs" (CLAUDE.md section 14). Deterministic, no LLM.

5 rounds; each shows a human-verified worked solution (bank `reconstruction`) with exactly one faulty step.
The student clicks the faulty line, then picks the reason from 3 options: the item's misconception (correct)
and 2 other misconceptions. Points + streak (the frontend hides them with calm_theme; no timer anywhere).
A WRONG reason that names misconception M is evidence for M in the student's maths posterior (bayes.update_lik).
"""
from __future__ import annotations

import random

import numpy as np
import yaml

from engine import ROOT, bayes, i18n


def conf() -> dict:
    return yaml.safe_load((ROOT / "games.yaml").read_text(encoding="utf-8"))["chasse_aux_erreurs"]


def _names(bank: dict, lang: str) -> dict[str, str]:
    key = {"fr": "name_fr", "ar": "name_ar"}.get(lang, "name_en")
    return {m["id"]: m.get(key) or m["name_en"] for m in bank["misconceptions"]}


def new_game(bank: dict, first: str | None = None) -> dict:
    """Pick the rounds: verified items of the configured topics, the diagnosed misconception first."""
    c = conf()
    items = [r for r in bank.get("reconstruction", []) if r.get("verified") and r["misconception"] in c["topics"]]
    rng = random.Random(c["seed"])
    rng.shuffle(items)
    if first:
        items.sort(key=lambda r: r["misconception"] != first)  # stable: diagnosed topic first
    rounds = []
    others_all = [t for t in c["topics"]]
    for k, r in enumerate(items[: c["rounds"]]):
        others = [t for t in others_all if t != r["misconception"]]
        distractors = random.Random(c["seed"] + k).sample(others, min(c["reason_options"] - 1, len(others)))
        opts = [r["misconception"], *distractors]
        random.Random(c["seed"] + 100 + k).shuffle(opts)
        rounds.append({"item": r, "reasons": {chr(65 + i): m for i, m in enumerate(opts)}})
    return {"rounds": rounds, "i": 0, "points": 0, "streak": 0, "best_streak": 0, "log": []}


def round_view(g: dict, bank: dict, lang: str) -> dict | None:
    if g["i"] >= len(g["rounds"]):
        return None
    rd = g["rounds"][g["i"]]
    problem, steps = i18n.reconstruction(rd["item"], lang)
    names = _names(bank, lang)
    return {"round": g["i"] + 1, "total": len(g["rounds"]), "item_id": rd["item"]["id"], "problem": problem,
            "steps": steps, "reasons": {k: names[m] for k, m in rd["reasons"].items()}}


def answer(g: dict, step: int, reason: str, diag: bayes.Diagnoser | None) -> dict:
    """Grade one round (deterministic) and update the maths posterior on a wrong reason."""
    c = conf()
    rd = g["rounds"][g["i"]]
    item = rd["item"]
    if not 1 <= int(step) <= len(item["worked_solution"]):
        raise ValueError(f"step must be between 1 and {len(item['worked_solution'])}")
    if reason not in rd["reasons"]:
        raise ValueError(f"unknown reason {reason!r}")
    step_ok = int(step) == item["error_step"]
    chosen = rd["reasons"][reason]
    reason_ok = chosen == item["misconception"]
    gained = (c["points_step"] if step_ok else 0) + (c["points_reason"] if reason_ok else 0)
    g["points"] += gained
    g["streak"] = g["streak"] + 1 if (step_ok and reason_ok) else 0
    g["best_streak"] = max(g["best_streak"], g["streak"])
    evidence = None
    if not reason_ok and diag is not None:
        lik = np.ones(len(bayes.H))
        lik[bayes.H.index(chosen)] = c["wrong_reason_lik"]
        lik = lik ** diag.p["tau"]
        diag.update_lik(lik, "game_wrong_reason", {"item": item["id"], "chosen": chosen})
        evidence = chosen
    g["log"].append({"item": item["id"], "step": int(step), "step_ok": step_ok, "reason": chosen,
                     "reason_ok": reason_ok, "points": gained, "evidence_for": evidence})
    g["i"] += 1
    return {"step_ok": step_ok, "reason_ok": reason_ok, "correct_step": item["error_step"],
            "correct_reason": item["misconception"], "points_gained": gained, "evidence_for": evidence}
