# features/executors/runtime.py

from acubed.features.algorithms.density import (
    duration_ms,
    notes_per_second,
    peak_nps,
)
from acubed.features.algorithms.jacks import (
    jack_density,
)
from acubed.features.algorithms.streams import (
    stream_density,
)
from acubed.features.definitions.difficulty import (
    DifficultyFeatures,
)
from acubed.models.gameplay import Stepfile


def build_features(
    chart_id: int,
    stepfile: Stepfile,
) -> DifficultyFeatures:

    return DifficultyFeatures(
        chart_id=chart_id,
        note_count=stepfile.length,
        duration_ms=duration_ms(stepfile),
        notes_per_second=notes_per_second(stepfile),
        peak_nps=peak_nps(stepfile),
        jack_density=jack_density(stepfile),
        stream_density=stream_density(stepfile),
    )
