# plugins/ffr/config.py

from dataclasses import dataclass, field

from acubed.domain.game.protocols import GameConfig
from acubed.infrastructure.ingestion.config import (
    RemoteAssetIngestionConfig,
    build_remote_asset_ingestion_config,
)


@dataclass(frozen=True)
class QuaverConfig(GameConfig):
    ingestion: RemoteAssetIngestionConfig = field(
        default_factory=lambda: build_remote_asset_ingestion_config(
            cache_namespace="quaver",
            asset_mode="direct",
            request_timeout=10.0,
        )
    )
    base_api_url: str = "https://api.quavergame.com/"

    @property
    def request_timeout(self) -> float:
        return self.ingestion.request_timeout

    @property
    def max_connections(self) -> int:
        return self.ingestion.max_connections

    @property
    def max_retries(self) -> int:
        return self.ingestion.max_retries

    @property
    def chart_max_retries(self) -> int:
        return self.ingestion.chart_max_retries

    @property
    def progress_log_seconds(self) -> float:
        return self.ingestion.progress_log_seconds
