from __future__ import annotations

from dataclasses import dataclass, field

from acubed.domain.game.protocols import GameConfig
from acubed.infrastructure.ingestion.config import (
    RemoteAssetIngestionConfig,
    build_remote_asset_ingestion_config,
)


@dataclass(frozen=True)
class OsuManiaConfig(GameConfig):
    ingestion: RemoteAssetIngestionConfig = field(
        default_factory=lambda: build_remote_asset_ingestion_config(
            cache_namespace="osumania",
            asset_mode="auto",
        )
    )
    base_api_url: str = "https://osu.ppy.sh/api/v2"
    web_base_url: str = "https://osu.ppy.sh"
    data_base_url: str = "https://data.ppy.sh"
    token_url: str = "https://osu.ppy.sh/oauth/token"
    search_sort: str = "plays_desc"
    pack_limit: int = 0

    @property
    def request_timeout(self) -> float:
        return self.ingestion.request_timeout

    @property
    def data_archive_timeout(self) -> float:
        return self.ingestion.archive_timeout

    @property
    def data_archive_max_members(self) -> int:
        return self.ingestion.archive_max_members

    @property
    def data_cache_dir(self) -> str:
        return self.ingestion.cache_dir

    @property
    def data_auto_min_charts(self) -> int:
        return self.ingestion.auto_min_charts

    @property
    def max_connections(self) -> int:
        return self.ingestion.max_connections

    @property
    def max_retries(self) -> int:
        return self.ingestion.max_retries

    @property
    def pack_asset_concurrency(self) -> int:
        return self.ingestion.pack_asset_concurrency

    @property
    def chart_asset_concurrency(self) -> int:
        return self.ingestion.chart_asset_concurrency

    @property
    def osu_extract_concurrency(self) -> int:
        return self.ingestion.extract_concurrency

    @property
    def direct_batch_size(self) -> int:
        return self.ingestion.batch_size

    @property
    def direct_max_retries(self) -> int:
        return self.ingestion.direct_max_retries

    @property
    def direct_fallback(self) -> bool:
        return self.ingestion.direct_fallback

    @property
    def asset_mode(self) -> str:
        return self.ingestion.asset_mode

    @property
    def progress_log_seconds(self) -> float:
        return self.ingestion.progress_log_seconds
