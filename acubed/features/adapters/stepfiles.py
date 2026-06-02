# features/adapters/stepfiles.py

from collections.abc import Iterable, Mapping
from typing import Any

from acubed.models.gameplay import Stepfile


def events_to_stepfile(
    rows: Iterable[Mapping[str, Any]],
) -> Stepfile:

    stepfile = Stepfile()

    for row in rows:
        stepfile.add_note(
            song_id=row["song_id"],
            note_id=row["note_id"],
            timestamp_ms=row["time"],
            lane=row["lane"],
        )

    return stepfile
