# features/algorithms/density.py

from acubed.models.gameplay import Stepfile


def duration_ms(
    stepfile: Stepfile,
) -> float:

    if stepfile.length < 2:
        return 0.0

    return stepfile.notes[-1].timestamp_ms - stepfile.notes[0].timestamp_ms


def notes_per_second(
    stepfile: Stepfile,
) -> float:

    duration = duration_ms(stepfile)

    if duration <= 0:
        return 0.0

    return stepfile.length / (duration / 1000)


def peak_nps(
    stepfile: Stepfile,
    window_ms: int = 1000,
) -> float:

    if stepfile.length == 0:
        return 0.0

    timestamps = [note.timestamp_ms for note in stepfile.notes]

    peak = 0

    left = 0

    for right in range(len(timestamps)):
        while timestamps[right] - timestamps[left] > window_ms:
            left += 1

        peak = max(
            peak,
            right - left + 1,
        )

    return float(peak)
