# features/algorithms/vertical_density.py

from collections.abc import Mapping

from acubed.models.gameplay import Note, Stepfile


def vertical_density(stepfile: Stepfile) -> Mapping[Note, float]:
    """
    Notes per second in the same lane.

    First note in each lane has density 0.
    """

    last_seen: dict = {}
    density: dict[Note, float] = {}

    for note in stepfile.notes:
        previous_time = last_seen.get(note.lane)

        if previous_time is None:
            density[note] = 0.0
        else:
            delta_ms = note.timestamp_ms - previous_time
            density[note] = 1000.0 / delta_ms

        last_seen[note.lane] = note.timestamp_ms

    return density
