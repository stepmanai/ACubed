from __future__ import annotations

from dataclasses import dataclass, field

from acubed.infrastructure.ingestion.config import (
    RemoteAssetIngestionConfig,
    RemoteGameConfig,
    build_remote_asset_ingestion_config,
)


@dataclass(frozen=True)
class OsuManiaConfig(RemoteGameConfig):
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
        return self.archive_timeout

    @property
    def data_archive_max_members(self) -> int:
        return self.archive_max_members

    @property
    def data_cache_dir(self) -> str:
        return self.cache_dir

    @property
    def data_auto_min_charts(self) -> int:
        return self.auto_min_charts

    @property
    def osu_extract_concurrency(self) -> int:
        return self.extract_concurrency

    @property
    def direct_batch_size(self) -> int:
        return self.batch_size
