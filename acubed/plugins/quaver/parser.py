from __future__ import annotations

from typing import Any

from acubed.domain.chart.types import Note, Stepfile
from acubed.domain.game.protocols import ChartParser


def _coerce_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None

    try:
        return int(value)
    except ValueError:
        try:
            return int(float(value))
        except ValueError:
            return None


def _parse_quaver_hitobjects(raw: bytes) -> list[dict[str, int]]:
    text = raw.decode("utf-8", errors="ignore")
    in_hitobjects = False
    current: dict[str, int] | None = None
    hitobjects: list[dict[str, int]] = []

    def finish_current() -> None:
        if current and "StartTime" in current:
            hitobjects.append(current)

    for raw_line in text.splitlines():
        stripped = raw_line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        if not in_hitobjects:
            if stripped == "HitObjects:":
                in_hitobjects = True
            continue

        if not raw_line.startswith((" ", "-")):
            break

        if stripped.startswith("- "):
            finish_current()
            current = {}
            stripped = stripped[2:].strip()

        if current is None or ":" not in stripped:
            continue

        key, value = stripped.split(":", 1)
        key = key.strip()

        if key not in {"StartTime", "EndTime", "Lane"}:
            continue

        parsed = _coerce_int(value)
        if parsed is not None:
            current[key] = parsed

    finish_current()
    return hitobjects


def parse_quaver_notes(raw: bytes, metadata: dict[str, Any] | None = None):
    hitobjects = _parse_quaver_hitobjects(raw)
    starts = [obj["StartTime"] for obj in hitobjects]
    if not starts:
        return

    min_start = min(starts)
    song_id = (
        metadata.get("map", {}).get("id")
        if metadata and isinstance(metadata.get("map"), dict)
        else None
    )

    for i, obj in enumerate(hitobjects):
        start = obj["StartTime"]
        end = obj.get("EndTime")
        lane = obj.get("Lane", 1)

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

        hitobjects = _parse_quaver_hitobjects(chart)
        starts = [obj["StartTime"] for obj in hitobjects]
        if not starts:
            return stepfile

        min_start = min(starts)
        song_id = (
            metadata.get("map", {}).get("id")
            if metadata and isinstance(metadata.get("map"), dict)
            else None
        )
        notes = stepfile.notes
        for note_id, obj in enumerate(hitobjects):
            start = obj["StartTime"]
            end = obj.get("EndTime")
            lane = obj.get("Lane", 1)

            notes.append(
                Note(
                    song_id=song_id,
                    note_id=note_id,
                    timestamp_ms=start - min_start,
                    lane=int(lane) - 1,
                    hold_duration=(end - start) if end is not None else 0,
                )
            )

        return stepfile
