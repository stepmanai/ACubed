from collections import defaultdict

import numpy as np

from acubed.features.types import NoteFeature


def normalize_length(n, k=3.0, x0=7.0):
    return 1 / (1 + np.exp(-k * (np.log(n) - x0)))


def strain_requirement(stepfile) -> NoteFeature:
    songs = defaultdict(list)
    for n in stepfile.notes:
        songs[n.song_id].append(n)

    density: NoteFeature = {}

    for _song_id, notes in songs.items():
        for note in sorted(notes, key=lambda n: n.timestamp_ms):
            density[note] = normalize_length(note.note_id)

    return density
