# features/definitions/difficulty.py

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DifficultyFeatures:
    chart_id: int

    note_count: int

    duration_ms: float

    notes_per_second: float

    peak_nps: float

    jack_density: float

    stream_density: float
