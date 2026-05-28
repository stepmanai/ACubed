# models/gameplay.py

from dataclasses import (
    dataclass,
    field,
)

from enum import IntEnum

from typing import Optional


class Orientation(IntEnum):
    LEFT = 0
    DOWN = 1
    UP = 2
    RIGHT = 3


@dataclass(
    frozen=True,
    slots=True,
)
class Note:
    timestamp_ms: float
    lane: int


@dataclass(slots=True)
class Stepfile:
    notes: list[Note] = field(
        default_factory=list
    )

    difficulty: float = 0.0

    @property
    def length(self):
        return len(self.notes)