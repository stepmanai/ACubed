from __future__ import annotations

import asyncio
from dataclasses import dataclass

from acubed.application.ingestion.engine import GameIngestionEngine
from acubed.domain.chart.types import AssetResponse, ChartRef, Pack, Stepfile
from acubed.domain.game.plugin import GamePlugin
from acubed.plugins.registry import discover_plugins


def test_all_bundled_plugins_build() -> None:
    registry = discover_plugins()

    assert registry.available() == ("etterna", "ffr", "osumania", "quaver")
    for game_id in registry.available():
        game = registry.get(game_id)
        assert game.id == game_id
        assert game.config.base_api_url
        assert callable(game.parser.parse)


@dataclass(frozen=True)
class _Config:
    base_api_url: str = "https://example.test"


class _Parser:
    def parse(self, response: AssetResponse) -> Stepfile:
        del response
        return Stepfile()


class _Source:
    def __init__(self, config: _Config):
        self.config = config
        self.closed = False

    async def fetch_packs(self, secrets=None):
        del secrets
        return [Pack(id="pack", name="Pack")]

    async def fetch_pack_charts(self, pack_id, secrets=None):
        del secrets
        return [
            ChartRef(
                id="chart",
                title="Chart",
                artist="Artist",
                pack_id=pack_id,
            )
        ]

    async def fetch_assets(self, chart_id, secrets=None):
        del secrets
        return AssetResponse(metadata={"id": chart_id}, raw_chart=b"chart")

    async def close(self) -> None:
        self.closed = True


def test_minimal_plugin_runs_through_ingestion_contract() -> None:
    plugin = GamePlugin(
        id="example",
        name="Example",
        config_factory=_Config,
        source_factory=_Source,
        parser_factory=_Parser,
    )
    game = plugin.build()

    assets = asyncio.run(GameIngestionEngine(game, concurrency=1).run())

    assert len(assets) == 1
    assert assets[0][0].id == "chart"
    assert game.source.closed
