# plugins/etterna/parser.py

from __future__ import annotations

from typing import Any

from acubed.domain.chart.types import Stepfile
from acubed.domain.game.protocols import ChartParser


def parse_etterna_notes(raw: bytes, metadata: dict[str, Any] | None = None):
    text = raw.decode("utf-8", errors="ignore")

    # --- Extract HitObjects block ---
    hitobjects_section = text.split("HitObjects:")[1]

    # --- Parse structured lines ---
    lines = [
        line.strip()
        for line in hitobjects_section.splitlines()
        if line.strip().startswith("-")
        or "StartTime" in line
        or "Lane" in line
        or "EndTime" in line
    ]

    objects = []
    current = {}

    for line in lines:
        if line.startswith("- StartTime"):
            # flush previous object
            if "start" in current:
                objects.append(current)
            current = {}

            current["start"] = float(line.split(":")[1].strip())

        elif "StartTime" in line:
            current["start"] = float(line.split(":")[1].strip())

        elif "Lane" in line:
            current["lane"] = int(line.split(":")[1].strip())

        elif "EndTime" in line:
            current["end"] = float(line.split(":")[1].strip())

    if "start" in current:
        objects.append(current)

    # --- compute min timestamp for normalization ---
    min_start = min(o["start"] for o in objects)

    # --- yield iterable notes ---
    for i, o in enumerate(objects):
        start = o["start"]
        lane = o.get("lane", 1) - 1  # zero-indexed
        end = o.get("end")

        yield {
            "song_id": metadata.get("map").get("id") if metadata else None,
            "note_id": i,
            "timestamp_ms": start - min_start,
            "lane": lane,
            "hold_duration": (end - start) if end is not None else 0,
        }


class EtternaChartParser(ChartParser):
    def parse(self, response) -> Stepfile:

        stepfile = Stepfile()

        if not response:
            return stepfile

        metadata, chart = response

        stepfile.difficulty = (
            metadata.get("difficulty_rating") if metadata else None
        )

        for note in parse_etterna_notes(chart, metadata):
            stepfile.add_note(**note)

        return stepfile
