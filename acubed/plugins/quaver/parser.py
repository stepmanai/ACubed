# plugins/ffr/parser.py

from __future__ import annotations

from typing import Any

from ruamel.yaml import YAML

from acubed.domain.chart.types import Stepfile
from acubed.domain.game.protocols import ChartParser


def parse_quaver_notes(raw: bytes, metadata: dict[str, Any] | None = None):
    yaml = YAML(typ="safe")

    text = raw.decode("utf-8", errors="ignore")
    data = yaml.load(text)

    if not data:
        return

    hitobjects = data.get("HitObjects") or []
    if not hitobjects:
        return

    starts = [
        obj.get("StartTime")
        for obj in hitobjects
        if isinstance(obj, dict) and obj.get("StartTime") is not None
    ]

    if not starts:
        return

    min_start = min(starts)

    song_id = (
        metadata.get("map", {}).get("id")
        if metadata and isinstance(metadata.get("map"), dict)
        else None
    )

    for i, obj in enumerate(hitobjects):
        if not isinstance(obj, dict):
            continue

        start = obj.get("StartTime")
        if start is None:
            continue

        end = obj.get("EndTime")

        lane = obj.get("Lane", 1)
        if lane is None:
            lane = 1

        yield {
            "song_id": song_id,
            "note_id": i,
            "timestamp_ms": start - min_start,
            "lane": int(lane) - 1,
            "hold_duration": (end - start) if end is not None else 0,
        }


class QuaverChartParser(ChartParser):
    def parse(self, response) -> Stepfile:

        stepfile = Stepfile()

        if not response:
            return stepfile

        metadata, chart = response

        stepfile.difficulty = (
            metadata.get("difficulty_rating") if metadata else None
        )

        for note in parse_quaver_notes(chart, metadata):
            stepfile.add_note(**note)

        return stepfile
