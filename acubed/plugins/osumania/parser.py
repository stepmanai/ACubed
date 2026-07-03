from __future__ import annotations

from typing import Any

from acubed.domain.chart.types import Note, Stepfile
from acubed.domain.game.protocols import ChartParser


def _osu_sections(raw: bytes) -> dict[str, list[str]]:
    text = raw.decode("utf-8-sig", errors="ignore")
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1]
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections.setdefault(current, []).append(stripped)

    return sections


def _osu_key_values(lines: list[str]) -> dict[str, str]:
    values = {}
    for line in lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def parse_osumania_notes(raw: bytes, metadata: dict[str, Any] | None = None):
    sections = _osu_sections(raw)
    general = _osu_key_values(sections.get("General", []))
    difficulty = _osu_key_values(sections.get("Difficulty", []))

    if _coerce_int(general.get("Mode"), -1) != 3:
        return

    keys = max(_coerce_int(difficulty.get("CircleSize"), 4), 1)
    hitobjects = sections.get("HitObjects", [])
    starts = []
    parsed = []

    for line in hitobjects:
        parts = line.split(",")
        if len(parts) < 5:
            continue

        x = _coerce_int(parts[0])
        start = _coerce_int(parts[2])
        object_type = _coerce_int(parts[3])
        lane = min(max(int(x * keys / 512), 0), keys - 1)
        end = None

        if object_type & 128 and len(parts) >= 6:
            end = _coerce_int(parts[5].split(":", 1)[0], start)

        starts.append(start)
        parsed.append((start, lane, end))

    if not parsed:
        return

    min_start = min(starts)
    song_id = None
    if metadata:
        song_id = metadata.get("id") or metadata.get("beatmap_id")

    for note_id, (start, lane, end) in enumerate(parsed):
        yield {
            "song_id": song_id,
            "note_id": note_id,
            "timestamp_ms": start - min_start,
            "lane": lane,
            "hold_duration": (end - start) if end is not None else 0,
        }


class OsuManiaChartParser(ChartParser):
    def parse(self, response) -> Stepfile:
        stepfile = Stepfile()

        if not response:
            return stepfile

        metadata, chart = response
        if isinstance(metadata, dict):
            stepfile.difficulty = _coerce_float(
                metadata.get("difficulty_rating")
                or metadata.get("difficulty")
                or 0.0
            )

        sections = _osu_sections(chart)
        general = _osu_key_values(sections.get("General", []))
        if _coerce_int(general.get("Mode"), -1) != 3:
            return stepfile

        for note in parse_osumania_notes(chart, metadata):
            stepfile.notes.append(Note(**note))

        stepfile.sort()
        return stepfile
