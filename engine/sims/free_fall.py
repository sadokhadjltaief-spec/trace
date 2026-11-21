"""Free fall with optional quadratic air drag. Misconception targeted: "heavier objects always fall faster".

Without drag the mass cancels: t = sqrt(2h/g) for every mass. With drag (same size and shape), the heavier
ball does land first: the misconception is the word "always".
"""
from __future__ import annotations

import numpy as np
from pydantic import Field
from scipy.integrate import solve_ivp

from engine.sims.base import G, Params, downsample, register

RHO_AIR = 1.2   # kg/m^3
CD_SPHERE = 0.47


class FreeFall(Params):
    mass_kg: float = Field(1.0, ge=0.05, le=50, json_schema_extra={"unit": "kg"})
    height_m: float = Field(20.0, ge=0.5, le=200, json_schema_extra={"unit": "m"})
    radius_m: float = Field(0.05, ge=0.01, le=0.5, json_schema_extra={"unit": "m"})
    air_drag: bool = Field(False, json_schema_extra={"unit": ""})


@register("free_fall", FreeFall)
def solve(p: FreeFall) -> dict:
    k = 0.5 * RHO_AIR * CD_SPHERE * np.pi * p.radius_m ** 2 if p.air_drag else 0.0

    def f(t, s):  # s = [y, v], y up, v up
        y, v = s
        return [v, -G - (k / p.mass_kg) * v * abs(v)]

    def ground(t, s):
        return s[0]
    ground.terminal, ground.direction = True, -1
    t_max = 10 * np.sqrt(2 * p.height_m / G) + 10
    sol = solve_ivp(f, (0, t_max), [p.height_m, 0.0], events=ground, max_step=t_max / 2000, rtol=1e-9, atol=1e-9)
    t_ground = float(sol.t_events[0][0]) if len(sol.t_events[0]) else float(sol.t[-1])
    v_imp = float(abs(sol.y_events[0][0][1])) if len(sol.t_events[0]) else float(abs(sol.y[1][-1]))
    t, y, v = downsample(sol.t, np.maximum(sol.y[0], 0), np.abs(sol.y[1]))
    return {"series": [{"name": "height", "unit": "m", "t": t, "y": y},
                       {"name": "speed", "unit": "m/s", "t": t, "y": v}],
            "result": {"time_to_ground_s": round(t_ground, 4), "impact_speed_m_s": round(v_imp, 4),
                       "no_drag_time_s": round(float(np.sqrt(2 * p.height_m / G)), 4)}}
