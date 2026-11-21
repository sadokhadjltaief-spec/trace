"""Whitelisted physics templates (CLAUDE.md section 13). Physics is COMPUTED (numpy/scipy), never generated.

Each template = a pydantic parameter schema (ranges + units, so out-of-range values are rejected) + a solver.
`run(template, params)` returns a JSON-ready dict: series to plot and scalar results.
"""
from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, ConfigDict

G = 9.81  # m/s^2


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


TEMPLATES: dict[str, tuple[type[Params], Callable]] = {}


def register(name: str, schema: type[Params]):
    def deco(fn):
        TEMPLATES[name] = (schema, fn)
        return fn
    return deco


def run(template: str, params: dict) -> dict:
    """Validate the parameters against the template's schema, solve, return {template, params, units, series, result}."""
    if template not in TEMPLATES:
        raise ValueError(f"unknown template {template!r} (whitelist: {sorted(TEMPLATES)})")
    schema, fn = TEMPLATES[template]
    p = schema(**params)  # raises pydantic.ValidationError when out of range
    out = fn(p)
    return {"template": template, "params": p.model_dump(), "units": units(schema), **out}


def units(schema: type[Params]) -> dict[str, str]:
    return {k: (f.json_schema_extra or {}).get("unit", "") for k, f in schema.model_fields.items()}


def schemas() -> dict[str, dict]:
    """JSON schema of every template (ranges + units) for the frontend sliders."""
    return {k: s.model_json_schema() for k, (s, _) in TEMPLATES.items()}


def downsample(t, *ys, n: int = 200):
    import numpy as np
    t = np.asarray(t)
    idx = np.unique(np.linspace(0, len(t) - 1, min(n, len(t))).astype(int))
    return [np.round(np.asarray(a)[idx], 5).tolist() for a in (t, *ys)]
