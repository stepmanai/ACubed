# features/algorithms/spatial_density.py

import contextvars
import math
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
# Judge window mass
# ------------------------------------------------------------


def compute_judge_window_mass(objective) -> float:
    """
    Weighted temporal support of the objective kernel.

    Units:
        reward * milliseconds
    """

    total = 0.0

    for tier in objective.judge_tiers:
        low, high = tier.window

        # continuous interval width
        width = high - low

        total += width * tier.reward

    return total


# ------------------------------------------------------------
# Normalization
# ------------------------------------------------------------


def normalize_spatial_density(
    x: float,
    notes_per_ms: float,
    objective=None,
) -> float:
    """
    Normalize weighted interaction count into [0, 1].

    Spatial density units:
        reward * note-count

    Judge mass units:
        reward * milliseconds

    We convert judge mass into expected interaction count via:

        judge_mass * notes_per_ms

    giving compatible units:

        reward * note-count
    """

    if objective is None:
        objective = get_objective()

    judge_mass = compute_judge_window_mass(objective)

    # expected interaction capacity
    scale = judge_mass * notes_per_ms

    # allow collapse toward zero
    scale = max(scale, 1e-12)

    # isolated notes near zero
    x = max(x - 1.0, 0.0)

    return 1.0 - math.exp(-x / scale)


# ------------------------------------------------------------
# Spatial density (O(n log n))
# ------------------------------------------------------------


def spatial_density(stepfile) -> NoteFeature:
    """
    Weighted local interaction density.

    Complexity:
        O(n log n)

    Definition:
        D(i) = Σ_tiers (
            count(notes within judge window)
            * tier reward
        )
    """

    objective = get_objective()

    # --------------------------------------------------------
    # Group by song
    # --------------------------------------------------------

    songs = defaultdict(list)

    for note in stepfile.notes:
        songs[note.song_id].append(note)

    result: NoteFeature = {}

    # --------------------------------------------------------
    # Compute independently per song
    # --------------------------------------------------------

    for _song_id, notes in songs.items():
        notes = sorted(
            notes,
            key=lambda n: n.timestamp_ms,
        )

        if not notes:
            continue

        times = [n.timestamp_ms for n in notes]

        # ----------------------------------------------------
        # Global chart density
        # ----------------------------------------------------

        duration_ms = max(
            times[-1] - times[0],
            1,
        )

        notes_per_ms = len(notes) / duration_ms

        # ----------------------------------------------------
        # Per-note density
        # ----------------------------------------------------

        for i, note in enumerate(notes):
            ti = times[i]
            acc = 0.0

            for tier in objective.judge_tiers:
                low, high = tier.window
                reward = tier.reward

                # relative -> absolute window
                start = ti - high
                end = ti - low

                # O(log n) boundary-safe range query
                left = bisect_left(times, start)
                right = bisect_right(times, end)

                count = right - left

                acc += count * reward

            result[note] = normalize_spatial_density(
                acc,
                notes_per_ms=notes_per_ms,
                objective=objective,
            )

    return result
