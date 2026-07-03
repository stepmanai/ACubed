"""Command-line entry point for chart ingestion."""

from __future__ import annotations

import argparse
import asyncio
import os
import threading
import time

from acubed.application.ingestion.engine import GameIngestionEngine
from acubed.application.persistence.repository import (
    ChartsRepository,
    DatabricksStepfileRepository,
    # NotesRepository,
)
from acubed.infrastructure.environment.secrets import get_required_secrets
from acubed.infrastructure.environment.types import is_databricks_environment
from acubed.infrastructure.logging import get_logger
from acubed.utils import (
    api_assets_to_bronze_tables,
    chart_refs_to_bronze_tables,
    packs_to_bronze_tables,
)


def _bronze_batch_size(game_id: str) -> int:
    """Get batch size with environment-aware defaults.

    Databricks Serverless benefits from larger batches (fewer Delta writes),
    while local development uses smaller batches for faster feedback.
    """
    from acubed.infrastructure.environment.detection import detect_environment

    env = detect_environment()
    high_volume_sources = {"etterna", "osumania"}
    if game_id in high_volume_sources:
        default = 5000 if is_databricks_environment(env) else 1000
    else:
        # Databricks: 1000 (10x larger for fewer MERGE operations)
        # Local: 100 (faster feedback, lower memory)
        default = 1000 if is_databricks_environment(env) else 100

    return max(int(os.getenv("BRONZE_BATCH_SIZE", default)), 1)


def _heartbeat_interval() -> float:
    return max(float(os.getenv("ACUBED_HEARTBEAT_SECONDS", "30")), 0)


def _skip_existing_source_enabled(game_id: str) -> bool:
    game_key = game_id.upper().replace("-", "_")
    game_value = os.getenv(f"{game_key}_SKIP_EXISTING_SOURCE")
    global_value = os.getenv("ACUBED_SKIP_EXISTING_SOURCE")

    if game_value is not None:
        return game_value.strip().lower() not in {"0", "false", "no"}
    if global_value is not None:
        return global_value.strip().lower() in {"1", "true", "yes"}

    return game_id in {"etterna", "osumania"}


def _sync_asset_charts_enabled(game_id: str) -> bool:
    game_key = game_id.upper().replace("-", "_")
    game_value = os.getenv(f"{game_key}_SYNC_ASSET_CHARTS")
    global_value = os.getenv("ACUBED_SYNC_ASSET_CHARTS")

    if game_value is not None:
        return game_value.strip().lower() in {"1", "true", "yes"}
    if global_value is not None:
        return global_value.strip().lower() in {"1", "true", "yes"}

    return game_id not in {"etterna", "osumania"}


def _stage_source_sync_enabled(game_id: str, environment) -> bool:
    game_key = game_id.upper().replace("-", "_")
    game_value = os.getenv(f"{game_key}_STAGE_SOURCE_SYNC")
    global_value = os.getenv("ACUBED_STAGE_SOURCE_SYNC")

    if game_value is not None:
        return game_value.strip().lower() not in {"0", "false", "no"}
    if global_value is not None:
        return global_value.strip().lower() in {"1", "true", "yes"}

    return game_id in {
        "etterna",
        "osumania",
    } and not is_databricks_environment(environment)


def _existing_nonempty_source_ids(storage, table_config, logger) -> set[str]:
    table_name = table_config.source

    if not storage.table_exists(table_name):
        return set()

    table = storage.read_table(table_name)
    columns = set(getattr(table, "columns", []) or [])
    required = {"_acubed_source_id", "chart_base64"}
    if not required.issubset(columns):
        logger.info(
            "Existing source table does not have skip columns: %s",
            ", ".join(sorted(required - columns)),
        )
        return set()

    # DuckDB relation
    if hasattr(table, "project") and hasattr(table, "filter"):
        rows = (
            table.filter("chart_base64 IS NOT NULL AND chart_base64 != ''")
            .project("_acubed_source_id")
            .distinct()
            .fetchall()
        )
        return {str(row[0]) for row in rows if row and row[0] is not None}

    # Spark DataFrame
    if hasattr(table, "select") and hasattr(table, "where"):
        rows = (
            table.select("_acubed_source_id")
            .where("chart_base64 IS NOT NULL AND chart_base64 != ''")
            .distinct()
            .collect()
        )
        return {
            str(row["_acubed_source_id"])
            for row in rows
            if row["_acubed_source_id"] is not None
        }

    logger.info("Storage table type does not support existing source skips")
    return set()


async def async_main(game_id: str | None = None) -> None:
    from acubed.runtime.app import ApplicationContext

    start_time = time.time()
    logger = get_logger()

    logger.info("=" * 80)
    logger.info("ACUBED INGESTION PIPELINE STARTED")
    logger.info("=" * 80)

    heartbeat_interval = _heartbeat_interval()
    heartbeat_stop = threading.Event()
    heartbeat_state = {
        "phase": "startup",
        "loaded_assets": 0,
        "pending_assets": 0,
        "pending_collections": 0,
        "pending_chart_refs": 0,
    }

    def heartbeat() -> None:
        if heartbeat_interval <= 0:
            return

        while not heartbeat_stop.wait(heartbeat_interval):
            elapsed = time.time() - start_time
            logger.info(
                "ACubed heartbeat: phase=%s elapsed=%.2fs "
                "loaded_assets=%d pending_assets=%d "
                "pending_collections=%d pending_chart_refs=%d",
                heartbeat_state["phase"],
                elapsed,
                heartbeat_state["loaded_assets"],
                heartbeat_state["pending_assets"],
                heartbeat_state["pending_collections"],
                heartbeat_state["pending_chart_refs"],
            )

    heartbeat_thread = threading.Thread(
        target=heartbeat,
        name="acubed-heartbeat",
        daemon=True,
    )
    heartbeat_thread.start()

    logger.info("Initializing application context")

    try:
        # single source of truth for config + game resolution
        app = ApplicationContext(game_override=game_id)
        game = app.runtime.game

        logger.info("Environment detected: %s", app.environment)
        logger.info("Selected game: %s (%s)", game.name, game.id)
        logger.info("Catalog: %s", getattr(app.storage, "catalog", "N/A"))
        logger.info("Schema: %s", getattr(app.storage, "schema", "N/A"))

        heartbeat_state["phase"] = "loading_secrets"
        logger.info("Loading required secrets")
        secrets = get_required_secrets(app.environment, game.required_secrets)
        logger.info("Loaded %d secret(s)", len(secrets))

        logger.info("Base API URL: %s", game.config.base_api_url)
        logger.info(
            "Request timeout: %s seconds",
            app.settings.runtime.request_timeout,
        )
        logger.info("Max retries: %s", app.settings.runtime.max_retries)
        logger.info(
            "Thread pool size: %s", app.settings.runtime.thread_pool_size
        )

        storage = app.storage
        table_config = app.table_config
        batch_size = _bronze_batch_size(game.id)
        sync_asset_charts = _sync_asset_charts_enabled(game.id)
        stage_source_sync = _stage_source_sync_enabled(
            game.id,
            app.environment,
        )
        source_staging_table = f"{table_config.source}__staging"

        logger.info("Bronze batch size: %d", batch_size)
        logger.info("Sync asset chart rows: %s", sync_asset_charts)
        logger.info("Stage source sync: %s", stage_source_sync)

        if is_databricks_environment(app.environment):
            repository = DatabricksStepfileRepository(
                storage,
                table_config,
                logger,
                workers=app.settings.runtime.thread_pool_size,
            )
        else:
            repository = ChartsRepository(storage, table_config, logger)

        if stage_source_sync and hasattr(storage, "drop_table"):
            storage.drop_table(source_staging_table)

        skip_source_ids: set[str] = set()
        if _skip_existing_source_enabled(game.id):
            heartbeat_state["phase"] = "checking_existing_source"
            check_start = time.time()
            skip_source_ids = _existing_nonempty_source_ids(
                storage,
                table_config,
                logger,
            )
            logger.info(
                "Found %d existing non-empty source row(s) to skip in %.2fs",
                len(skip_source_ids),
                time.time() - check_start,
            )

        engine = GameIngestionEngine(
            game=game,
            secrets=secrets,
            concurrency=app.settings.runtime.thread_pool_size,
            skip_source_ids=skip_source_ids,
        )

        ingest_start = time.time()
        loaded_assets = 0
        pending_assets = []
        pending_collections = []
        pending_chart_refs = []

        def update_heartbeat(phase: str) -> None:
            heartbeat_state["phase"] = phase
            heartbeat_state["loaded_assets"] = loaded_assets
            heartbeat_state["pending_assets"] = len(pending_assets)
            heartbeat_state["pending_collections"] = len(pending_collections)
            heartbeat_state["pending_chart_refs"] = len(pending_chart_refs)

        def flush_pending(optimize: bool = False) -> None:
            nonlocal loaded_assets
            nonlocal pending_assets, pending_collections, pending_chart_refs

            if (
                not pending_assets
                and not pending_collections
                and not pending_chart_refs
            ):
                return

            update_heartbeat("bronze_transform")
            collection_batch = pending_collections
            chart_ref_batch = pending_chart_refs
            asset_batch = pending_assets
            pending_collections = []
            pending_chart_refs = []
            pending_assets = []

            collection_etl = packs_to_bronze_tables(collection_batch)
            chart_ref_etl = chart_refs_to_bronze_tables(chart_ref_batch)
            asset_etl = api_assets_to_bronze_tables(asset_batch)
            chart_rows = list(chart_ref_etl.charts)
            if sync_asset_charts:
                chart_rows.extend(asset_etl.charts)

            update_heartbeat("bronze_sync")
            if is_databricks_environment(app.environment):
                repository.sync_bronze_tables(
                    collections=collection_etl.collections,
                    charts=chart_rows,
                    source=asset_etl.source,
                    optimize=optimize,
                )
            else:
                repository.sync_collections(collection_etl.collections)
                repository.sync_charts(chart_rows)
                if stage_source_sync:
                    repository.stage_source(
                        source_staging_table,
                        asset_etl.source,
                    )
                else:
                    repository.sync_source(asset_etl.source)

            loaded_assets += len(asset_batch)
            update_heartbeat("streaming")
            logger.info("Bronze streamed: %d API asset(s)", loaded_assets)

        update_heartbeat("streaming")
        async for event_type, payload in engine.stream():
            if event_type == "collections":
                pending_collections.extend(payload)
            elif event_type == "chart_refs":
                pending_chart_refs.extend(payload)
            elif event_type == "assets":
                pending_assets.extend(payload)

            update_heartbeat(f"received_{event_type}")
            if event_type in {"collections", "chart_refs"}:
                flush_pending()
            elif len(pending_assets) >= batch_size:
                flush_pending()

        flush_pending()

        if stage_source_sync:
            update_heartbeat("source_stage_merge")
            logger.info("Merging staged source rows")
            repository.merge_staged_source(source_staging_table)
            if hasattr(storage, "drop_table"):
                storage.drop_table(source_staging_table)

        if is_databricks_environment(app.environment) and loaded_assets:
            update_heartbeat("optimize")
            logger.info("Optimizing bronze Delta tables")
            storage.optimize_tables(
                (
                    table_config.collections,
                    table_config.charts,
                    table_config.source,
                )
            )

        ingest_elapsed = time.time() - ingest_start
        logger.info(
            "Ingested and streamed %d API asset(s) in %.2f seconds",
            loaded_assets,
            ingest_elapsed,
        )

        elapsed = time.time() - start_time

        logger.info("=" * 80)
        logger.info("INGESTION COMPLETED IN %.2f SECONDS", elapsed)
        logger.info("=" * 80)
    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run acubed chart ingestion.")
    parser.add_argument(
        "--game",
        default="ffr",
        help="Game id to ingest.",
    )

    args, _ = parser.parse_known_args()

    asyncio.run(async_main(game_id=args.game))


if __name__ == "__main__":
    main()
