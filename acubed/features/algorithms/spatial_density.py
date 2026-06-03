import contextvars
from bisect import bisect_left, bisect_right
from collections import defaultdict

from acubed.engine.objectives.ffr import FFR_OBJECTIVE
from acubed.features.types import NoteFeature

# ------------------------------------------------------------
# Context
# ------------------------------------------------------------

OBJECTIVE_CTX = contextvars.ContextVar(
    "spatial_density_objective",
    default=FFR_OBJECTIVE,
)


def set_spatial_objective(objective) -> None:
    OBJECTIVE_CTX.set(objective)


def get_objective():
    return OBJECTIVE_CTX.get()


# ------------------------------------------------------------
# Spatial density (OPTIMIZED)
# ------------------------------------------------------------


def spatial_density(stepfile) -> NoteFeature:
    objective = get_objective()

    songs = defaultdict(list)
    for n in stepfile.notes:
        songs[n.song_id].append(n)

    result: NoteFeature = {}

    for _song_id, notes in songs.items():
        notes = sorted(notes, key=lambda n: n.timestamp_ms)
        times = [n.timestamp_ms for n in notes]

        for i, ni in enumerate(notes):
            ti = times[i]
            acc = 0.0

            for tier in objective.judge_tiers:
                low, high = tier.window
                reward = tier.reward

                start = ti - high
                end = ti - low

                left = bisect_left(times, start)
                right = bisect_right(times, end)

                acc += (right - left) * reward

            result[ni] = acc

    return result
