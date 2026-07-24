# plugins/ffr/config.py

from dataclasses import dataclass, field

from acubed.infrastructure.ingestion.config import (
    RemoteAssetIngestionConfig,
    RemoteGameConfig,
    build_remote_asset_ingestion_config,
)


@dataclass(frozen=True)
class QuaverConfig(RemoteGameConfig):
    ingestion: RemoteAssetIngestionConfig = field(
        default_factory=lambda: build_remote_asset_ingestion_config(
            cache_namespace="quaver",
            asset_mode="direct",
            request_timeout=10.0,
        )
    )
    base_api_url: str = "https://api.quavergame.com/"
