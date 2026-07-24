"""Interfaces implemented by game plugins."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable, Sequence
from typing import Protocol, runtime_checkable

from acubed.domain.chart.types import AssetResponse, ChartRef, Pack, Stepfile


@runtime_checkable
class ChartParser(Protocol):
    def parse(self, response: AssetResponse) -> Stepfile: ...


@runtime_checkable
class ChartSource(Protocol):
    async def fetch_packs(
        self, secrets: dict[str, str] | None = None
    ) -> Iterable[Pack]: ...

    async def fetch_pack_charts(
        self, pack_id: str, secrets: dict[str, str] | None = None
    ) -> Iterable[ChartRef]: ...

    async def fetch_assets(
        self, chart_id: str, secrets: dict[str, str] | None = None
    ) -> AssetResponse: ...

    async def close(self) -> None: ...


@runtime_checkable
class BulkPackChartSource(Protocol):
    async def fetch_charts_for_packs(
        self,
        packs: Sequence[Pack],
        *,
        secrets: dict[str, str],
        concurrency: int,
    ) -> Iterable[ChartRef]: ...


@runtime_checkable
class BulkAssetSource(Protocol):
    async def fetch_many(
        self,
        charts: Sequence[ChartRef],
        secrets: dict[str, str],
        *,
        concurrency: int,
    ) -> list[tuple[ChartRef, AssetResponse]]: ...


@runtime_checkable
class StreamingAssetSource(Protocol):
    def stream_many(
        self,
        charts: Sequence[ChartRef],
        secrets: dict[str, str],
        *,
        concurrency: int,
    ) -> AsyncIterator[list[tuple[ChartRef, AssetResponse]]]: ...


@runtime_checkable
class PackNameResolver(Protocol):
    def resolve_pack_name(self, pack_id: str) -> str: ...


@runtime_checkable
class PackPayloadResolver(Protocol):
    def resolve_pack_payload(self, pack_id: str) -> dict | None: ...


class GameConfig(Protocol):
    base_api_url: str
