"""Command-line entry point for chart ingestion."""

from __future__ import annotations

import argparse
import asyncio
import os
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


def _bronze_batch_size() -> int:
    return max(int(os.getenv("BRONZE_BATCH_SIZE", 100)), 1)


async def async_main(game_id: str | None = None) -> None:
    from acubed.runtime.app import ApplicationContext

    start_time = time.time()
    logger = get_logger()

    logger.info("=" * 80)
    logger.info("ACUBED INGESTION PIPELINE STARTED")
    logger.info("=" * 80)

    logger.info("Initializing application context")

    # single source of truth for config + game resolution
    app = ApplicationContext(game_override=game_id)
    game = app.runtime.game

    logger.info("Environment detected: %s", app.environment)
    logger.info("Selected game: %s (%s)", game.name, game.id)
    logger.info("Catalog: %s", getattr(app.storage, "catalog", "N/A"))
    logger.info("Schema: %s", getattr(app.storage, "schema", "N/A"))

    logger.info("Loading required secrets")
    secrets = get_required_secrets(app.environment, game.required_secrets)
    logger.info("Loaded %d secret(s)", len(secrets))

    logger.info("Base API URL: %s", game.config.base_api_url)
    logger.info(
        "Request timeout: %s seconds", app.settings.runtime.request_timeout
    )
    logger.info("Max retries: %s", app.settings.runtime.max_retries)
    logger.info("Thread pool size: %s", app.settings.runtime.thread_pool_size)

    engine = GameIngestionEngine(
        game=game,
        secrets=secrets,
        concurrency=app.settings.runtime.thread_pool_size,
    )

    storage = app.storage
    table_config = app.table_config
    batch_size = _bronze_batch_size()

    if is_databricks_environment(app.environment):
        repository = DatabricksStepfileRepository(
            storage,
            table_config,
            logger,
            workers=app.settings.runtime.thread_pool_size,
        )
    else:
        repository = ChartsRepository(storage, table_config, logger)

    # =========================================================
    # STEP 1: INGEST + STREAM BRONZE LOAD
    # =========================================================
    ingest_start = time.time()
    loaded_assets = 0
    pending_assets = []
    pending_collections = []
    pending_chart_refs = []

    def flush_pending(optimize: bool = False) -> None:
        nonlocal loaded_assets
        nonlocal pending_assets, pending_collections, pending_chart_refs

        if (
            not pending_assets
            and not pending_collections
            and not pending_chart_refs
        ):
            return

        collection_batch = pending_collections
        chart_ref_batch = pending_chart_refs
        asset_batch = pending_assets
        pending_collections = []
        pending_chart_refs = []
        pending_assets = []

        collection_etl = packs_to_bronze_tables(collection_batch)
        chart_ref_etl = chart_refs_to_bronze_tables(chart_ref_batch)
        asset_etl = api_assets_to_bronze_tables(asset_batch)

        if is_databricks_environment(app.environment):
            repository.sync_bronze_tables(
                collections=collection_etl.collections,
                charts=chart_ref_etl.charts + asset_etl.charts,
                source=asset_etl.source,
                optimize=optimize,
            )
        else:
            repository.sync_collections(collection_etl.collections)
            repository.sync_charts(chart_ref_etl.charts + asset_etl.charts)
            repository.sync_source(asset_etl.source)

        loaded_assets += len(asset_batch)
        logger.info("Bronze streamed: %d API asset(s)", loaded_assets)

    async for event_type, payload in engine.stream():
        if event_type == "collections":
            pending_collections.extend(payload)
        elif event_type == "chart_refs":
            pending_chart_refs.extend(payload)
        elif event_type == "assets":
            pending_assets.extend(payload)

        if event_type in {"collections", "chart_refs"}:
            flush_pending()
        elif len(pending_assets) >= batch_size:
            flush_pending()

    flush_pending()

    if is_databricks_environment(app.environment) and loaded_assets:
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

    # API parsing and silver writes are disabled while bronze chart tables are
    # being built.
    # api_assets = await engine.run()
    # etl = stepfiles_to_tables(stepfiles)
    # notes_repo = NotesRepository(storage, table_config, logger)
    # notes_repo.sync_notes(etl.notes)

    # =========================================================
    # DONE
    # =========================================================
    elapsed = time.time() - start_time

    logger.info("=" * 80)
    logger.info("INGESTION COMPLETED IN %.2f SECONDS", elapsed)
    logger.info("=" * 80)


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
