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


# 3. Refactor vertical_density

# Current (guessing):

# def vertical_density(
#     stepfile: Stepfile,
# ) -> float:
#     ...

# Replace with:

# acubed/features/algorithms/vertical_density.py
# import narwhals as nw


# def vertical_density(
#     events: nw.DataFrame | nw.LazyFrame,
# ) -> nw.DataFrame | nw.LazyFrame:

#     return (
#         events
#         .sort("time")
#         .with_columns(
#             nw.col("time")
#             .diff()
#             .alias("delta_time")
#         )
#     )

# Obviously replace the implementation with your actual logic.

# The key change is:

# Stepfile

# becomes

# nw.DataFrame | nw.LazyFrame
