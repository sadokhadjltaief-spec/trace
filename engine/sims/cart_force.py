"""Cart pushed by a constant force for a while (Newton's 2nd law), optional kinetic friction.
Misconceptions targeted: "motion needs a constant force" (a constant force gives a constant speed; the cart
slows down without a force) and "no force means no motion" (the cart stops as soon as the push stops).

During the push: a = (F - mu m g) / m (if F overcomes friction). After the push: a = -mu g while moving, so
without friction the speed stays constant.
"""
from __future__ import annotations

import numpy as np
from pydantic import Field
from scipy.integrate import solve_ivp

from engine.sims.base import G, Params, downsample, register


class CartForce(Params):
    mass_kg: float = Field(2.0, ge=0.1, le=50, json_schema_extra={"unit": "kg"})
    force_n: float = Field(4.0, ge=0, le=100, json_schema_extra={"unit": "N"})
    push_s: float = Field(2.0, ge=0, le=20, json_schema_extra={"unit": "s"})
    friction_mu: float = Field(0.0, ge=0, le=1, json_schema_extra={"unit": ""})
    duration_s: float = Field(6.0, ge=1, le=60, json_schema_extra={"unit": "s"})


def _phase(p: CartForce, t0: float, t1: float, x0: float, v0: float, force: float):
    """Integrate one phase; a terminal event stops the cart when friction brings it to rest."""
    fr = p.friction_mu * G

    def f(t, s):
        v = s[1]
        a = force / p.mass_kg - (fr if v > 1e-9 else 0.0)
        if v <= 1e-9 and force / p.mass_kg <= fr:  # at rest and the push cannot overcome static friction
            a = 0.0
        return [v, a]

    def stops(t, s):
        return s[1] - 1e-7
    stops.terminal, stops.direction = True, -1
    if t1 <= t0:
        return np.array([t0]), np.array([[x0], [v0]]), False
    sol = solve_ivp(f, (t0, t1), [x0, v0], events=stops if (fr > 0 and force == 0) else None,
                    max_step=(t1 - t0) / 400, rtol=1e-9, atol=1e-10)
    stopped = bool(sol.status == 1)
    return sol.t, sol.y, stopped


@register("cart_force", CartForce)
def solve(p: CartForce) -> dict:
    t_push = min(p.push_s, p.duration_s)
    t1, y1, _ = _phase(p, 0.0, t_push, 0.0, 0.0, p.force_n)
    v_end_push = float(y1[1][-1])
    t2, y2, stopped = _phase(p, t_push, p.duration_s, float(y1[0][-1]), v_end_push, 0.0)
    stop_time = float(t2[-1]) if stopped else None
    T, X, V = [t1, t2], [y1[0], y2[0]], [y1[1], y2[1]]
    if stopped and t2[-1] < p.duration_s:  # at rest until the end
        T.append(np.array([p.duration_s]))
        X.append(np.array([y2[0][-1]]))
        V.append(np.array([0.0]))
    t, x, v = (np.concatenate(a) for a in (T, X, V))
    v = np.where(np.abs(v) < 1e-6, 0.0, v)
    tt, xx, vv = downsample(t, x, v, n=300)
    return {"series": [{"name": "speed", "unit": "m/s", "t": tt, "y": vv},
                       {"name": "position", "unit": "m", "t": tt, "y": xx}],
            "result": {"speed_end_of_push_m_s": round(v_end_push, 4),
                       "speed_at_end_m_s": round(float(v[-1]), 4),
                       "stop_time_s": round(stop_time, 4) if stop_time is not None else None,
                       "distance_m": round(float(x[-1]), 4)}}
