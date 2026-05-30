# features/algorithms/jacks.py

from acubed.models.gameplay import Stepfile


def jack_density(
    stepfile: Stepfile,
) -> float:

    if stepfile.length < 2:
        return 0.0

    jacks = 0

    previous = stepfile.notes[0]

    for current in stepfile.notes[1:]:
        if current.lane == previous.lane:
            jacks += 1

        previous = current

    return jacks / stepfile.length
