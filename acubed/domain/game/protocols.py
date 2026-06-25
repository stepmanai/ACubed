"""Interfaces implemented by game plugins."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from acubed.domain.chart.types import AssetResponse, ChartRef, Pack, Stepfile


class ChartParser(Protocol):
    def parse(self, response: AssetResponse) -> Stepfile: ...


class ChartSource(Protocol):
    async def fetch_packs(self) -> Iterable[Pack]: ...

    async def fetch_pack_charts(self, pack_id: str) -> Iterable[ChartRef]: ...

    async def fetch_assets(
        self, chart_id: str, secrets: dict[str, str] | None = None
    ) -> AssetResponse: ...

    async def close(self) -> None: ...


class PackSource(ChartSource, Protocol):
    pass


class GameConfig(Protocol):
    base_api_url: str


GameBuilder = Any
