# engine/objective.py

from dataclasses import dataclass

from acubed.engine.judge import JudgeTier


@dataclass(frozen=True, slots=True)
class Objective:
    name: str
    judge_tiers: tuple[JudgeTier, ...]

    def max_kernel_radius(self) -> int:
        return max(
            max(abs(t.window[0]) for t in self.judge_tiers),
            max(abs(t.window[1]) for t in self.judge_tiers),
        )
