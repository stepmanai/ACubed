# models/domain.py

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Note:
    chart_id: str
    note_id: int
    lane: int
    timestamp_ms: float


@dataclass(frozen=True, slots=True)
class HitEvent:
    player_id: str
    note_id: int
    offset_ms: float
