from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from acubed.domain.chart.types import AssetResponse, ChartRef, Pack


@dataclass
class ETLResult:
    collections: list[dict]
    charts: list[dict]
    source: list[dict]


def _json_safe(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, bytes):
        encoded = base64.b64encode(value).decode("ascii")
        return encoded

    if isinstance(value, bytearray):
        encoded = base64.b64encode(bytes(value)).decode("ascii")
        return encoded

    if isinstance(value, dict):
        return {k: _json_safe(v, key=str(k)) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [_json_safe(item, key=key) for item in value]

    return value


def _base64_source(value: Any) -> str:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, bytearray):
        payload = bytes(value)
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")

    return base64.b64encode(payload).decode("ascii")


def _strip_chart_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_chart_data(child)
            for key, child in value.items()
            if str(key).lower() != "chart"
        }

    if isinstance(value, list):
        return [_strip_chart_data(item) for item in value]

    return _json_safe(value)


# API parsing is disabled while bronze chart tables are being built.
# def _raw_payload_for_stepfile(stepfile: Stepfile) -> dict[str, Any]:
#     payload = stepfile.raw_api_payload
#
#     if isinstance(payload, dict):
#         return _json_safe(payload)
#
#     return {}


def _raw_payload_for_asset(response: AssetResponse) -> dict[str, Any]:
    if isinstance(response.raw_payload, dict):
        return _json_safe(response.raw_payload)

    return _json_safe(
        {
            "metadata": response.metadata,
            "chart": response.raw_chart,
        }
    )


def _json_payload(value: Any) -> str:
    return json.dumps(
        _json_safe(value),
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _difficulty_value(raw_payload: Any) -> float | None:
    if not isinstance(raw_payload, dict):
        return None

    value = raw_payload.get("difficulty")
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def packs_to_bronze_tables(packs: list[Pack]) -> ETLResult:
    collections = [
        {
            "_acubed_collection_id": pack.id,
            "collection_name": pack.name,
            "api_payload": _json_payload(
                pack.raw_payload
                or {
                    "id": pack.id,
                    "name": pack.name,
                }
            ),
        }
        for pack in packs
    ]

    return ETLResult(collections=collections, charts=[], source=[])


def chart_refs_to_bronze_tables(charts: list[ChartRef]) -> ETLResult:
    chart_rows = [
        {
            "_acubed_chart_id": chart.id,
            "_acubed_song_id": (
                chart.raw_payload.get("_acubed_song_id")
                if isinstance(chart.raw_payload, dict)
                else None
            ),
            "_acubed_collection_id": chart.pack_id,
            "chart_title": chart.title,
            "chart_artist": chart.artist,
            "difficulty_name": (
                chart.raw_payload.get("difficulty_name")
                if isinstance(chart.raw_payload, dict)
                else None
            ),
            "difficulty": _difficulty_value(chart.raw_payload),
            "keys": (
                chart.raw_payload.get("keys")
                if isinstance(chart.raw_payload, dict)
                else None
            ),
            "api_payload": _json_payload(
                _strip_chart_data(
                    chart.raw_payload
                    or {
                        "id": chart.id,
                        "title": chart.title,
                        "artist": chart.artist,
                        "pack_id": chart.pack_id,
                    }
                )
            ),
        }
        for chart in charts
    ]

    return ETLResult(collections=[], charts=chart_rows, source=[])


def _source_rows_for_asset(
    chart: ChartRef,
    response: AssetResponse,
) -> list[dict]:
    return [
        {
            "_acubed_source_id": chart.id,
            "_acubed_chart_id": chart.id,
            "_acubed_collection_id": chart.pack_id,
            "chart_base64": _base64_source(response.raw_chart),
        }
    ]


def api_assets_to_bronze_tables(
    assets: list[tuple[ChartRef, AssetResponse]],
) -> ETLResult:
    charts = [
        {
            "_acubed_chart_id": chart.id,
            "_acubed_song_id": (
                chart.raw_payload.get("_acubed_song_id")
                if isinstance(chart.raw_payload, dict)
                else None
            ),
            "_acubed_collection_id": chart.pack_id,
            "chart_title": chart.title,
            "chart_artist": chart.artist,
            "difficulty_name": (
                chart.raw_payload.get("difficulty_name")
                if isinstance(chart.raw_payload, dict)
                else None
            ),
            "difficulty": _difficulty_value(chart.raw_payload),
            "keys": (
                chart.raw_payload.get("keys")
                if isinstance(chart.raw_payload, dict)
                else None
            ),
            "api_payload": _json_payload(
                {
                    "chart_ref": _strip_chart_data(
                        chart.raw_payload
                        or {
                            "id": chart.id,
                            "title": chart.title,
                            "artist": chart.artist,
                            "pack_id": chart.pack_id,
                        }
                    ),
                    "asset": _strip_chart_data(
                        _raw_payload_for_asset(response)
                    ),
                }
            ),
        }
        for chart, response in assets
    ]
    source = [
        source_row
        for chart, response in assets
        for source_row in _source_rows_for_asset(chart, response)
    ]

    return ETLResult(collections=[], charts=charts, source=source)


# API parsing is disabled while bronze chart tables are being built.
# def stepfiles_to_tables(stepfiles: list[Stepfile]) -> ETLResult:
#     charts: list[dict] = []
#     notes: list[dict] = []
#     append_chart = charts.append
#     append_note = notes.append
#
#     for sf in stepfiles:
#         sf_notes = sf.notes
#         song_id = sf_notes[0].song_id if sf_notes else sf.source_chart_id
#
#         append_chart(
#             {
#                 "_acubed_chart_id": sf.source_chart_id or str(song_id),
#                 "api_payload": json.dumps(
#                     _raw_payload_for_stepfile(sf),
#                     ensure_ascii=True,
#                     separators=(",", ":"),
#                 ),
#             }
#         )
#
#         if not sf_notes:
#             continue
#
#         for note in sf_notes:
#             append_note(
#                 {
#                     "song_id": note.song_id,
#                     "note_id": note.note_id,
#                     "timestamp_ms": note.timestamp_ms,
#                     "lane": note.lane,
#                     "hold_duration": note.hold_duration,
#                 }
#             )
#
#     return ETLResult(collections=[], charts=charts, source=notes)
