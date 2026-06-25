# plugins/ffr/parser.py


from acubed.domain.chart.types import Stepfile
from acubed.domain.game.protocols import ChartParser


class FFRChartParser(ChartParser):
    def parse(self, response) -> Stepfile:
        stepfile = Stepfile()

        if not response:
            return stepfile

        metadata, chart = response

        if isinstance(chart, (bytes, str)):
            import json

            chart = json.loads(chart)

        if not isinstance(chart, list):
            raise ValueError(f"Unexpected chart format: {type(chart)}")

        stepfile.difficulty = metadata.get("difficulty") if metadata else None

        start_timestamp_ms = min(row[3] for row in chart if len(row) >= 4)

        for note_id, row in enumerate(chart, start=1):
            if len(row) < 4:
                continue

            _, lane, _, timestamp_ms = row

            stepfile.add_note(
                song_id=metadata.get("id") if metadata else None,
                note_id=note_id,
                timestamp_ms=timestamp_ms - start_timestamp_ms,
                lane=lane,
                hold_duration=0,
            )

        return stepfile
