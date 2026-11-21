"""Simple pendulum (exact nonlinear equation, no damping). Misconception targeted: "the period depends on the mass".

theta'' = -(g/L) sin(theta): the mass is not in the equation, so the period does not depend on it.
Small angles: T = 2 pi sqrt(L/g).
"""
from __future__ import annotations

import numpy as np
from pydantic import Field
from scipy.integrate import solve_ivp

from engine.sims.base import G, Params, downsample, register


class Pendulum(Params):
    length_m: float = Field(1.0, ge=0.1, le=5, json_schema_extra={"unit": "m"})
    mass_kg: float = Field(1.0, ge=0.01, le=20, json_schema_extra={"unit": "kg"})
    amplitude_deg: float = Field(10.0, ge=1, le=60, json_schema_extra={"unit": "deg"})
    duration_s: float = Field(10.0, ge=2, le=30, json_schema_extra={"unit": "s"})


@register("pendulum", Pendulum)
def solve(p: Pendulum) -> dict:
    th0 = np.radians(p.amplitude_deg)

    def f(t, s):
        return [s[1], -(G / p.length_m) * np.sin(s[0])]  # note: no mass

    def up_cross(t, s):  # theta crosses 0 going up -> one full period between consecutive events
        return s[0]
    up_cross.direction = 1
    sol = solve_ivp(f, (0, p.duration_s), [th0, 0.0], events=up_cross, max_step=0.005, rtol=1e-10, atol=1e-10)
    ev = sol.t_events[0]
    period = float(np.mean(np.diff(ev))) if len(ev) >= 2 else float("nan")
    # energy per unit mass (should be conserved): g L (1 - cos th) + 0.5 L^2 w^2
    e = G * p.length_m * (1 - np.cos(sol.y[0])) + 0.5 * (p.length_m * sol.y[1]) ** 2
    t, th = downsample(sol.t, np.degrees(sol.y[0]), n=400)
    return {"series": [{"name": "angle", "unit": "deg", "t": t, "y": th}],
            "result": {"period_s": round(period, 4),
                       "small_angle_period_s": round(float(2 * np.pi * np.sqrt(p.length_m / G)), 4),
                       "energy_drift_rel": round(float((e.max() - e.min()) / e[0]), 8) if e[0] else 0.0}}
