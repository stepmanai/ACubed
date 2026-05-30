# features/adapters/charts/ffr.py

from acubed.models.gameplay import (
    Stepfile,
)


def ffr_to_stepfile(chart: list[list[int]]) -> Stepfile:
    stepfile = Stepfile()

    if not chart:
        return stepfile

    start_timestamp_ms = min(row[3] for row in chart)

    for _, lane, _, timestamp_ms in chart:
        stepfile.add_note(
            timestamp_ms - start_timestamp_ms,
            lane,
        )

    return stepfile
