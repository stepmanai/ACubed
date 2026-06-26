from __future__ import annotations

from dataclasses import dataclass

from acubed.domain.chart.types import Stepfile


@dataclass
class ETLResult:
    charts: list[dict]
    notes: list[dict]


def stepfiles_to_tables(stepfiles: list[Stepfile]) -> ETLResult:
    charts: list[dict] = []
    notes: list[dict] = []
    append_chart = charts.append
    append_note = notes.append

    for sf in stepfiles:
        sf_notes = sf.notes
        if not sf_notes:
            continue

        song_id = sf_notes[0].song_id

        append_chart(
            {
                "song_id": song_id,
                "difficulty": sf.difficulty,
                "note_count": len(sf_notes),
            }
        )

        for note in sf_notes:
            append_note(
                {
                    "song_id": note.song_id,
                    "note_id": note.note_id,
                    "timestamp_ms": note.timestamp_ms,
                    "lane": note.lane,
                    "hold_duration": note.hold_duration,
                }
            )

    return ETLResult(charts=charts, notes=notes)
