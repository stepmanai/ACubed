from dataclasses import dataclass

from acubed.domain.chart.types import Stepfile


@dataclass
class ETLResult:
    charts: list[dict]
    notes: list[dict]


def stepfiles_to_tables(stepfiles: list[Stepfile]) -> ETLResult:
    charts: list[dict] = []
    notes: list[dict] = []

    for sf in stepfiles:
        if not sf.notes:
            continue

        song_id = sf.notes[0].song_id

        charts.append(
            {
                "song_id": song_id,
                "difficulty": sf.difficulty,
                "note_count": len(sf.notes),
            }
        )

        for note in sf.notes:
            notes.append(
                {
                    "song_id": note.song_id,
                    "note_id": note.note_id,
                    "timestamp_ms": note.timestamp_ms,
                    "lane": note.lane,
                    "hold_duration": note.hold_duration,
                }
            )

    return ETLResult(charts=charts, notes=notes)
