"""Predict - Observe - Explain on top of the simulations (CLAUDE.md section 13).

1. Predict: a multiple-choice prediction (+ confidence tap). Options map to physics misconceptions; the answer
   updates a PHYSICS posterior with the same Bayesian engine as the maths questions (engine/bayes.py).
2. Observe: the simulation runs with the item's parameters. The correct option is COMPUTED from the result
   (never stored, never generated): grading method "simulation".
3. Explain: the student says why the result differs (stored for the teacher; no LLM grading), then a transfer
   prediction with different parameters, graded the same way.
Items: data/bank/physics.json (hand-written). Only items ticked in data/bank/physics_review.md are verified.
"""
from __future__ import annotations

import functools
import json
import re

from engine import ROOT, bayes
from engine.sims.base import run

BANK = ROOT / "data" / "bank" / "physics.json"
REVIEW = ROOT / "data" / "bank" / "physics_review.md"
TOL = 0.005  # relative difference below which two times/periods count as "the same"


@functools.lru_cache(maxsize=1)
def _raw() -> dict:
    return json.loads(BANK.read_text(encoding="utf-8"))


def approved() -> set[str]:
    if not REVIEW.exists():
        return set()
    return set(re.findall(r"^- \[[xX]\] (\S+)", REVIEW.read_text(encoding="utf-8"), re.M))


def misconceptions() -> list[dict]:
    return _raw()["misconceptions"]


def runs(item: dict) -> dict[str, dict]:
    return {label: run(item["template"], p) for label, p in item["runs"].items()}


def outcome(item: dict, res: dict[str, dict] | None = None) -> str:
    """The observed outcome, computed from the simulation results."""
    res = res or runs(item)
    k = item["kind"]
    if k in ("compare_landing", "compare_period"):
        key = "time_to_ground_s" if k == "compare_landing" else "period_s"
        a, b = res["a"]["result"][key], res["b"]["result"][key]
        if abs(a - b) <= TOL * max(a, b):
            return "same"
        if k == "compare_landing":
            return "a_first" if a < b else "b_first"
        return "a_longer" if a > b else "b_longer"
    r = res["a"]
    speed = next(s for s in r["series"] if s["name"] == "speed")
    push = r["params"]["push_s"]
    if k == "during_push":
        vs = [v for t, v in zip(speed["t"], speed["y"]) if 0 < t <= push]
        d = vs[-1] - vs[0]
        return "increases" if d > 1e-3 else "decreases" if d < -1e-3 else "constant"
    if k == "after_push":
        res_ = r["result"]
        if res_["stop_time_s"] is not None:
            return "stops_at_once" if res_["stop_time_s"] - push < 0.05 else "slows_and_stops"
        dv = res_["speed_at_end_m_s"] - res_["speed_end_of_push_m_s"]
        return "constant_speed" if abs(dv) < 1e-3 else ("speeds_up" if dv > 0 else "slows_and_stops")
    raise ValueError(f"unknown item kind {k!r}")


@functools.lru_cache(maxsize=1)
def items() -> dict[str, dict]:
    """Items with the correct option computed by simulation; `verified` from the human review ticks."""
    ok = approved()
    out = {}
    for it in _raw()["items"]:
        res = runs(it)
        oc = outcome(it, res)
        correct = [k for k, o in it["options"].items() if o["outcome"] == oc]
        if len(correct) != 1:
            raise ValueError(f"{it['id']}: {len(correct)} options match the computed outcome {oc!r}")
        out[it["id"]] = {**it, "correct": correct[0], "observed": oc, "verified": it["id"] in ok}
    return out


def live_items(allow_unverified: bool) -> list[dict]:
    its = list(items().values())
    return [i for i in its if i["verified"]] or (its if allow_unverified else [])


def table(its: list[dict]) -> bayes.Table:
    """Likelihood table for the physics posterior (bank items look like maths questions to bayes.py)."""
    qs = [{"id": i["id"], "options": {k: k for k in i["options"]}, "correct": i["correct"],
           "option_misconception": i.get("option_misconception", {})} for i in its]
    return bayes.build_table(qs)


def write_review() -> None:
    """data/bank/physics_review.md: one tick box per item, keeping existing ticks."""
    ok = approved()
    lines = ["# Physics bank review (data/bank/physics.json)", "",
             "Tick `- [x] ID` to approve an item. The correct answer below was COMPUTED by the simulation.", ""]
    for i in items().values():
        opts = "; ".join(f"{k}: {o['text']['en']}" + (f" [{i['option_misconception'].get(k)}]"
                                                      if k in i.get("option_misconception", {}) else "")
                         for k, o in i["options"].items())
        lines += [f"- [{'x' if i['id'] in ok else ' '}] {i['id']}  ({i['template']}, target {i['target']})",
                  f"  - {i['text']['en']}", f"  - options: {opts}",
                  f"  - computed outcome: {i['observed']} -> correct option {i['correct']}", ""]
    REVIEW.write_text("\n".join(lines), encoding="utf-8")
