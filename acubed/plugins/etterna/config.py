# plugins/etterna/config.py

from __future__ import annotations

from dataclasses import dataclass, field

from acubed.infrastructure.ingestion.config import (
    RemoteAssetIngestionConfig,
    RemoteGameConfig,
    build_remote_asset_ingestion_config,
)


@dataclass(frozen=True)
class EtternaConfig(RemoteGameConfig):
    ingestion: RemoteAssetIngestionConfig = field(
        default_factory=lambda: build_remote_asset_ingestion_config(
            cache_namespace="etterna",
            asset_mode="auto",
        )
    )
    base_api_url: str = "https://api.etternaonline.com/api"
    google_drive_folder_id: str = "14l_PXmYsahLm3DQRgQMu5gprdc1LJNXS"
    google_credentials_path: str | None = (
        r"/home/wirrywoo/ACubed/credentials.json"
    )
    allow_full_zip_fallback: bool = False

    @property
    def sm_fetch_concurrency(self) -> int:
        return self.extract_concurrency

    @property
    def data_cache_dir(self) -> str:
        return self.cache_dir

    @property
    def data_archive_timeout(self) -> float:
        return self.archive_timeout

    @property
    def data_auto_min_charts(self) -> int:
        return self.auto_min_charts

    @property
    def direct_batch_size(self) -> int:
        return self.batch_size
