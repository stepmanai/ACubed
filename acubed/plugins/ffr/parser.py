from __future__ import annotations

import json

from acubed.domain.chart.types import Note, Stepfile
from acubed.domain.game.protocols import ChartParser


class FFRChartParser(ChartParser):
    def parse(self, response) -> Stepfile:
        stepfile = Stepfile()

        if not response:
            return stepfile

        metadata, chart = response

        if isinstance(chart, (bytes, str)):
            chart = json.loads(chart)

        if not isinstance(chart, list):
            raise ValueError(f"Unexpected chart format: {type(chart)}")

        rows = [row for row in chart if len(row) >= 4]
        if not rows:
            return stepfile

        song_id = metadata.get("id") if metadata else None
        stepfile.difficulty = metadata.get("difficulty") if metadata else None

        start_timestamp_ms = min(row[3] for row in rows)
        notes = stepfile.notes

        for note_id, row in enumerate(rows, start=1):
            notes.append(
                Note(
                    song_id=song_id,
                    note_id=note_id,
                    timestamp_ms=row[3] - start_timestamp_ms,
                    lane=row[1],
                    hold_duration=0,
                )
            )

        return stepfile
