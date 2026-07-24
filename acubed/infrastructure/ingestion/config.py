from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RemoteAssetIngestionConfig:
    request_timeout: float
    archive_timeout: float
    archive_max_members: int
    cache_dir: str
    auto_min_charts: int
    max_connections: int
    max_retries: int
    chart_max_retries: int
    page_concurrency: int
    pack_asset_concurrency: int
    chart_asset_concurrency: int
    extract_concurrency: int
    batch_size: int
    direct_max_retries: int
    direct_fallback: bool
    asset_mode: str
    progress_log_seconds: float


class RemoteGameConfig:
    """Compatibility accessors shared by remote game configurations."""

    ingestion: RemoteAssetIngestionConfig

    @property
    def request_timeout(self) -> float:
        return self.ingestion.request_timeout

    @property
    def archive_timeout(self) -> float:
        return self.ingestion.archive_timeout

    @property
    def archive_max_members(self) -> int:
        return self.ingestion.archive_max_members

    @property
    def cache_dir(self) -> str:
        return self.ingestion.cache_dir

    @property
    def auto_min_charts(self) -> int:
        return self.ingestion.auto_min_charts

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
    def page_concurrency(self) -> int:
        return self.ingestion.page_concurrency

    @property
    def pack_asset_concurrency(self) -> int:
        return self.ingestion.pack_asset_concurrency

    @property
    def chart_asset_concurrency(self) -> int:
        return self.ingestion.chart_asset_concurrency

    @property
    def extract_concurrency(self) -> int:
        return self.ingestion.extract_concurrency

    @property
    def batch_size(self) -> int:
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


def build_remote_asset_ingestion_config(
    *,
    cache_namespace: str,
    request_timeout: float = 30.0,
    archive_timeout: float = 3600.0,
    archive_max_members: int = 0,
    auto_min_charts: int = 10000,
    max_connections: int = 128,
    max_retries: int = 5,
    chart_max_retries: int = 10,
    page_concurrency: int = 16,
    pack_asset_concurrency: int = 4,
    chart_asset_concurrency: int = 32,
    extract_concurrency: int = 128,
    batch_size: int = 1000,
    direct_max_retries: int = 10,
    direct_fallback: bool = True,
    asset_mode: str = "auto",
    progress_log_seconds: float = 30.0,
) -> RemoteAssetIngestionConfig:
    return RemoteAssetIngestionConfig(
        request_timeout=request_timeout,
        archive_timeout=archive_timeout,
        archive_max_members=archive_max_members,
        cache_dir=f".cache/acubed/{cache_namespace}",
        auto_min_charts=auto_min_charts,
        max_connections=max_connections,
        max_retries=max_retries,
        chart_max_retries=chart_max_retries,
        page_concurrency=page_concurrency,
        pack_asset_concurrency=pack_asset_concurrency,
        chart_asset_concurrency=chart_asset_concurrency,
        extract_concurrency=extract_concurrency,
        batch_size=batch_size,
        direct_max_retries=direct_max_retries,
        direct_fallback=direct_fallback,
        asset_mode=asset_mode.strip().lower(),
        progress_log_seconds=progress_log_seconds,
    )
