# plugins/ffr/config.py

from dataclasses import dataclass, field

from acubed.infrastructure.ingestion.config import (
    RemoteAssetIngestionConfig,
    RemoteGameConfig,
    build_remote_asset_ingestion_config,
)


@dataclass(frozen=True)
class FFRConfig(RemoteGameConfig):
    ingestion: RemoteAssetIngestionConfig = field(
        default_factory=lambda: build_remote_asset_ingestion_config(
            cache_namespace="ffr",
            asset_mode="direct",
            chart_asset_concurrency=4,
        )
    )
    base_api_url: str = "https://www.flashflashrevolution.com/api/api.php"

    playlist_url: str = (
        "https://www.flashflashrevolution.com/game/r3/r3-playlist.php"
    )
