# features/algorithms/temporal_density.py


from acubed.features.types import NoteFeature
from acubed.models.gameplay import Note, Stepfile


def temporal_density(stepfile: Stepfile) -> NoteFeature:
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
        elif note.timestamp_ms == previous_time:
            density[note] = float("inf")
        else:
            delta_ms = note.timestamp_ms - previous_time
            density[note] = 1000.0 / delta_ms

        last_seen[note.lane] = note.timestamp_ms

    return density
