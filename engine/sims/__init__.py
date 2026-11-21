"""Physics simulations: whitelisted templates (base.py) and the Predict-Observe-Explain flow (poe.py)."""
from engine.sims import cart_force, free_fall, pendulum  # noqa: F401  (registers the templates)
from engine.sims.base import TEMPLATES, run, schemas  # noqa: F401
