# features/algorithms/temporal_density.py

import math
from collections import defaultdict

from acubed.features.types import NoteFeature


def normalize_temporal_density(
    x: float,
    k: float = 5.0,
) -> float:

    if math.isinf(x):
        return 1.0

    return 1.0 - math.exp(-x / k)


def temporal_density(stepfile) -> NoteFeature:
    songs = defaultdict(list)
    for n in stepfile.notes:
        songs[n.song_id].append(n)

    density: NoteFeature = {}

    for _song_id, notes in songs.items():
        last_seen = {}

        for note in sorted(notes, key=lambda n: n.timestamp_ms):
            prev = last_seen.get(note.lane)

            if prev is None:
                density[note] = 0.0
            elif note.timestamp_ms == prev:
                density[note] = 1.0
            else:
                delta = note.timestamp_ms - prev
                density[note] = normalize_temporal_density(1000.0 / delta)

            last_seen[note.lane] = note.timestamp_ms

    return density
