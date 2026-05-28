# engine/judge.py

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JudgeTier:
    name: str
    window: tuple[int, int]
    reward: float