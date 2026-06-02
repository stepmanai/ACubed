from dataclasses import replace

from acubed.models.gameplay import Stepfile


def apply_rate(
    stepfile: Stepfile,
    rate: float = 1.0,
) -> Stepfile:

    adjusted = Stepfile()

    adjusted.notes = [
        replace(
            note,
            timestamp_ms=note.timestamp_ms / rate,
        )
        for note in stepfile.notes
    ]

    return adjusted
