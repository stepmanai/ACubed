# engine/rulesets/ffr.py

from acubed.engine.judge import JudgeTier
from acubed.engine.objective import Objective
from acubed.engine.ruleset import Ruleset

FFR_OBJECTIVE = Objective(
    name="ffr_default",
    judge_tiers=(
        JudgeTier(
            name="average",
            window=(-117, -83),
            reward=0.1,
        ),
        JudgeTier(
            name="good",
            window=(-83, -50),
            reward=0.5,
        ),
        JudgeTier(
            name="perfect",
            window=(-50, -17),
            reward=1.0,
        ),
        JudgeTier(
            name="amazing",
            window=(-17, 17),
            reward=1.0,
        ),
        JudgeTier(
            name="perfect",
            window=(17, 50),
            reward=1.0,
        ),
        JudgeTier(
            name="good",
            window=(50, 118),
            reward=0.5,
        ),
    ),
)


FFR_RULESET = Ruleset(
    name="ffr",
    objective=FFR_OBJECTIVE,
)
