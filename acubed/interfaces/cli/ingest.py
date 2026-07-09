"""Command-line entry point for chart ingestion."""

from __future__ import annotations

import argparse
import asyncio
import threading
import time
from pathlib import Path

from acubed.application.ingestion.engine import GameIngestionEngine
from acubed.application.persistence.repository import (
    ChartsRepository,
    DatabricksStepfileRepository,
    # NotesRepository,
)
from acubed.infrastructure.environment.secrets import get_required_secrets
from acubed.infrastructure.environment.types import is_databricks_environment
from acubed.infrastructure.logging import (
    close_progress,
    console_info,
    console_svg_logo,
    finish_progress,
    get_logger,
    log_event,
    set_progress_message,
    set_progress_status,
)
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

    return max(default, 1)


def _heartbeat_interval() -> float:
    return 0.0


def _skip_existing_source_enabled(game_id: str) -> bool:
    return game_id in {"etterna", "osumania"}


def _sync_asset_charts_enabled(game_id: str) -> bool:
    return game_id not in {"etterna", "osumania"}


def _stage_source_sync_enabled(game_id: str, environment) -> bool:
    return game_id in {
        "etterna",
        "osumania",
    } and not is_databricks_environment(environment)


def _plugin_logo_path(game_id: str) -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "plugins"
        / game_id
        / "assets"
        / "logo.svg"
    )


def _existing_nonempty_source_ids(storage, table_config, logger) -> set[str]:
    table_name = table_config.source

    if not storage.table_exists(table_name):
        return set()

    table = storage.read_table(table_name)
    columns = set(getattr(table, "columns", []) or [])
    required = {"_acubed_source_id", "chart_base64"}
    if not required.issubset(columns):
        log_event(
            logger,
            "source_skip_check",
            status="skipped",
            reason="missing_columns",
            missing_columns=",".join(sorted(required - columns)),
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

    log_event(
        logger,
        "source_skip_check",
        status="skipped",
        reason="unsupported_storage_table_type",
    )
    return set()


async def async_main(game_id: str | None = None) -> None:
    from acubed.runtime.app import ApplicationContext

    start_time = time.time()
    logger = get_logger()
    progress_finished = False

    console_info("ACubed ingest starting")

    heartbeat_interval = _heartbeat_interval()
    heartbeat_stop = threading.Event()
    heartbeat_state = {
        "phase": "startup",
        "action": "initialize",
        "loaded_assets": 0,
        "pending_assets": 0,
        "pending_collections": 0,
        "pending_chart_refs": 0,
        "last_event": "none",
    }

    def heartbeat() -> None:
        if heartbeat_interval <= 0:
            return

        while not heartbeat_stop.wait(heartbeat_interval):
            elapsed = time.time() - start_time
            log_event(
                logger,
                "heartbeat",
                phase=heartbeat_state["phase"],
                action=heartbeat_state["action"],
                last_event=heartbeat_state["last_event"],
                elapsed_seconds=elapsed,
                loaded_assets=heartbeat_state["loaded_assets"],
                pending_assets=heartbeat_state["pending_assets"],
                pending_collections=heartbeat_state["pending_collections"],
                pending_chart_refs=heartbeat_state["pending_chart_refs"],
            )

    heartbeat_thread = threading.Thread(
        target=heartbeat,
        name="acubed-heartbeat",
        daemon=True,
    )
    heartbeat_thread.start()

    log_event(
        logger, "pipeline", status="starting", action="initialize_context"
    )

    try:
        # single source of truth for config + game resolution
        app = ApplicationContext(game_override=game_id)
        game = app.runtime.game
        console_svg_logo(_plugin_logo_path(game.id), title=game.name)
        set_progress_status("Initializing ingestion", 0.0)

        log_event(
            logger,
            "runtime_config",
            environment=app.environment,
            game_id=game.id,
            game_name=game.name,
            catalog=getattr(app.storage, "catalog", "N/A"),
            schema=getattr(app.storage, "schema", "N/A"),
        )

        heartbeat_state["phase"] = "loading_secrets"
        heartbeat_state["action"] = "load_required_secrets"
        set_progress_status("Loading secrets", 0.02)
        log_event(
            logger,
            "secrets",
            status="starting",
            required_count=len(game.required_secrets),
        )
        secrets = get_required_secrets(app.environment, game.required_secrets)
        log_event(
            logger, "secrets", status="completed", loaded_count=len(secrets)
        )

        log_event(
            logger,
            "ingestion_settings",
            base_api_url=game.config.base_api_url,
            request_timeout_seconds=app.settings.runtime.request_timeout,
            max_retries=app.settings.runtime.max_retries,
            thread_pool_size=app.settings.runtime.thread_pool_size,
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

        log_event(
            logger,
            "bronze_settings",
            batch_size=batch_size,
            sync_asset_chart_rows=sync_asset_charts,
            stage_source_sync=stage_source_sync,
            source_staging_table=source_staging_table
            if stage_source_sync
            else None,
        )

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
            set_progress_status("Preparing source staging", 0.04)
            heartbeat_state["phase"] = "source_stage_prepare"
            heartbeat_state["action"] = "drop_existing_source_staging_table"
            log_event(
                logger,
                "source_stage",
                status="starting",
                action="drop_staging_table",
                table=source_staging_table,
            )
            storage.drop_table(source_staging_table)
            log_event(
                logger,
                "source_stage",
                status="completed",
                action="drop_staging_table",
                table=source_staging_table,
            )

        skip_source_ids: set[str] = set()
        if _skip_existing_source_enabled(game.id):
            set_progress_status("Checking existing source rows", 0.06)
            heartbeat_state["phase"] = "checking_existing_source"
            heartbeat_state["action"] = "read_existing_nonempty_source_ids"
            check_start = time.time()
            log_event(
                logger,
                "source_skip_check",
                status="starting",
                table=table_config.source,
            )
            skip_source_ids = _existing_nonempty_source_ids(
                storage,
                table_config,
                logger,
            )
            log_event(
                logger,
                "source_skip_check",
                status="completed",
                rows=len(skip_source_ids),
                elapsed_seconds=time.time() - check_start,
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

        def update_heartbeat(phase: str, action: str | None = None) -> None:
            heartbeat_state["phase"] = phase
            if action is not None:
                heartbeat_state["action"] = action
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

            update_heartbeat("bronze_transform", "transform_pending_batches")
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

            log_event(
                logger,
                "bronze_flush",
                status="starting",
                collections=len(collection_batch),
                chart_refs=len(chart_ref_batch),
                assets=len(asset_batch),
                chart_rows=len(chart_rows),
                source_rows=len(asset_etl.source),
                staged_source=stage_source_sync,
                optimize=optimize,
            )

            update_heartbeat("bronze_sync", "sync_bronze_tables")
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
            update_heartbeat("streaming", "consume_ingestion_events")
            log_event(
                logger,
                "bronze_flush",
                status="completed",
                loaded_assets=loaded_assets,
                collections=len(collection_batch),
                chart_refs=len(chart_ref_batch),
                assets=len(asset_batch),
            )

        update_heartbeat("streaming", "consume_ingestion_events")
        set_progress_status("Fetching source metadata", 0.08)
        async for event_type, payload in engine.stream():
            heartbeat_state["last_event"] = event_type
            if event_type == "collections":
                pending_collections.extend(payload)
            elif event_type == "chart_refs":
                pending_chart_refs.extend(payload)
            elif event_type == "assets":
                pending_assets.extend(payload)

            log_event(
                logger,
                "engine_event",
                event_type=event_type,
                rows=len(payload),
                pending_collections=len(pending_collections),
                pending_chart_refs=len(pending_chart_refs),
                pending_assets=len(pending_assets),
            )
            update_heartbeat(f"received_{event_type}", f"handle_{event_type}")
            if event_type in {"collections", "chart_refs"}:
                set_progress_message("Writing metadata to bronze")
                flush_pending()
            elif len(pending_assets) >= batch_size:
                set_progress_message("Writing source rows to bronze")
                flush_pending()

        set_progress_message("Finalizing bronze writes")
        flush_pending()
        set_progress_status("Finalizing bronze writes", 0.94)

        if stage_source_sync:
            set_progress_status("Merging staged source rows", 0.96)
            update_heartbeat("source_stage_merge", "merge_staged_source_rows")
            log_event(
                logger,
                "source_stage",
                status="starting",
                action="merge_staged_rows",
                table=source_staging_table,
            )
            repository.merge_staged_source(source_staging_table)
            if hasattr(storage, "drop_table"):
                storage.drop_table(source_staging_table)
            log_event(
                logger,
                "source_stage",
                status="completed",
                action="merge_staged_rows",
                table=source_staging_table,
            )

        if is_databricks_environment(app.environment) and loaded_assets:
            set_progress_status("Optimizing bronze tables", 0.98)
            update_heartbeat("optimize", "optimize_bronze_delta_tables")
            log_event(
                logger, "optimize", status="starting", target="bronze_tables"
            )
            storage.optimize_tables(
                (
                    table_config.collections,
                    table_config.charts,
                    table_config.source,
                )
            )
            log_event(
                logger, "optimize", status="completed", target="bronze_tables"
            )

        ingest_elapsed = time.time() - ingest_start
        elapsed = time.time() - start_time
        log_event(
            logger,
            "pipeline",
            status="completed",
            loaded_assets=loaded_assets,
            ingest_elapsed_seconds=ingest_elapsed,
            elapsed_seconds=elapsed,
        )

        finish_progress("Ingestion complete")
        progress_finished = True
        console_info("ACubed ingest completed in %.2fs", elapsed)
    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=5)
        if not progress_finished:
            close_progress()


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
