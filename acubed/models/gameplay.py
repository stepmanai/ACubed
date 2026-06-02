# models/gameplay.py

from dataclasses import dataclass, field
from enum import IntEnum


class Orientation(IntEnum):
    LEFT = 0
    DOWN = 1
    UP = 2
    RIGHT = 3


@dataclass(frozen=True, slots=True)
class Note:
    song_id: int
    note_id: int
    timestamp_ms: float
    lane: Orientation


@dataclass(slots=True)
class Stepfile:
    notes: list[Note] = field(default_factory=list)
    difficulty: float = 0.0

    @property
    def length(self) -> int:
        return len(self.notes)

    def add_note(
        self,
        song_id: int,
        note_id: int,
        timestamp_ms: float,
        lane: Orientation | int,
    ) -> None:
        if not isinstance(lane, Orientation):
            lane = Orientation(lane)

        self.notes.append(
            Note(
                song_id=song_id,
                note_id=note_id,
                timestamp_ms=timestamp_ms,
                lane=lane,
            )
        )

    def sort(self) -> None:
        self.notes.sort(key=lambda note: note.timestamp_ms)
