# features/adapters/charts.py

from acubed.models.gameplay import (
    Note,
    Stepfile,
)


def chart_to_stepfile(
    chart_events: list[list],
    difficulty: float = 0.0,
) -> Stepfile:

    notes = []

    for event in chart_events:
        notes.append(
            Note(
                timestamp_ms=float(event[3]),
                lane=int(event[1]),
            )
        )

    return Stepfile(
        notes=notes,
        difficulty=difficulty,
    )
