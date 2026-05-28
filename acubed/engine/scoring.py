# engine/scoring.py

from acubed.engine.objective import Objective


def score_hit(offset_ms: float, objective: Objective) -> tuple[str, float]:
    for tier in objective.judge_tiers:
        lower, upper = tier.window

        if lower <= offset_ms < upper:
            return tier.name, tier.reward

    return "miss", 0.0