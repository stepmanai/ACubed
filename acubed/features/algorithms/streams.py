# features/algorithms/streams.py

from acubed.models.gameplay import Stepfile


def stream_density(
    stepfile: Stepfile,
    threshold_ms: float = 200.0,
) -> float:

    if stepfile.length < 2:
        return 0.0

    stream_intervals = 0

    total_intervals = 0

    previous = stepfile.notes[0]

    for current in stepfile.notes[1:]:
        interval = current.timestamp_ms - previous.timestamp_ms

        if interval <= threshold_ms:
            stream_intervals += 1

        total_intervals += 1

        previous = current

    return stream_intervals / total_intervals if total_intervals else 0.0
