# features/adapters/charts/ffr.py

from acubed.models.gameplay import (
    Stepfile,
)


def ffr_to_stepfile(chart: list[list[int]]) -> Stepfile:
    stepfile = Stepfile()

    if not chart:
        return stepfile

    start_timestamp_ms = min(row[3] for row in chart)

    for note_id, (_, lane, _, timestamp_ms) in enumerate(chart, start=1):
        stepfile.add_note(
            song_id=0,  # Replace with actual song ID if available
            note_id=note_id,
            timestamp_ms=timestamp_ms - start_timestamp_ms,
            lane=lane,
        )

    return stepfile
