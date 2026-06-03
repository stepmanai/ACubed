# engine/judge.py

from dataclasses import dataclass
from enum import Enum


class Boundary(Enum):
    INCLUSIVE = "inclusive"
    LEFT_INCLUSIVE = "left_inclusive"
    RIGHT_INCLUSIVE = "right_inclusive"
    EXCLUSIVE = "exclusive"


@dataclass(frozen=True, slots=True)
class JudgeTier:
    name: str
    window: tuple[int, int]
    reward: float
    boundary: Boundary = Boundary.LEFT_INCLUSIVE


def in_window(t, start, end, boundary):
    if boundary == Boundary.INCLUSIVE:
        return start <= t <= end
    elif boundary == Boundary.LEFT_INCLUSIVE:
        return start <= t < end
    elif boundary == Boundary.RIGHT_INCLUSIVE:
        return start < t <= end
    else:
        return start < t < end
