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
        cache_dir=f".cache/{cache_namespace}",
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
