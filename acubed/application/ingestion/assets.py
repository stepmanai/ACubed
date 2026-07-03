from __future__ import annotations

from acubed.domain.chart.types import AssetResponse, ChartRef


def empty_asset_response(
    chart: ChartRef,
    *,
    source_file_name: str = "",
) -> AssetResponse:
    metadata = dict(chart.raw_payload or {})
    metadata.setdefault("id", chart.id)
    metadata.setdefault("pack_id", chart.pack_id)
    metadata["source_file_name"] = source_file_name

    return AssetResponse(
        metadata=metadata,
        raw_chart=b"",
        raw_payload={**metadata, "chart": b""},
    )
