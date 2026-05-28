# engine/objective.py

from dataclasses import dataclass

from acubed.engine.judge import JudgeTier


@dataclass(frozen=True, slots=True)
class Objective:
    name: str
    judge_tiers: tuple[JudgeTier, ...]