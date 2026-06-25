"""Chart domain types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple


@dataclass(frozen=True)
class Note:
    song_id: int
    note_id: int
    timestamp_ms: float
    lane: int
    hold_duration: float = 0

    def __hash__(self):
        return hash((self.song_id, self.note_id))

    def __eq__(self, other):
        if not isinstance(other, Note):
            return False
        return (self.song_id, self.note_id) == (other.song_id, other.note_id)


@dataclass
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
        lane: int,
        hold_duration: float,
    ) -> None:

        self.notes.append(
            Note(
                song_id=song_id,
                note_id=note_id,
                timestamp_ms=timestamp_ms,
                lane=lane,
                hold_duration=hold_duration,
            )
        )

    def sort(self) -> None:
        self.notes.sort(key=lambda note: note.timestamp_ms)


@dataclass(frozen=True)
class Pack:
    id: str
    name: str


@dataclass(frozen=True)
class ChartRef:
    id: str
    title: str
    artist: str
    pack_id: str


class AssetResponse(NamedTuple):
    metadata: bytes
    raw_chart: bytes
