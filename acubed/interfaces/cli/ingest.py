"""Command-line entry point for chart ingestion."""

import argparse
import asyncio
import os
import time

from acubed.application.ingestion.engine import GameIngestionEngine
from acubed.application.persistence.repository import (
    ChartsRepository,
    NotesRepository,
)
from acubed.infrastructure.environment.secrets import get_required_secrets
from acubed.infrastructure.logging import get_logger
from acubed.utils import stepfiles_to_tables


async def async_main(game_id: str | None = None) -> None:
    if game_id:
        os.environ["GAME"] = game_id

    from acubed.runtime.app import ApplicationContext

    start_time = time.time()
    logger = get_logger()

    logger.info("=" * 80)
    logger.info("ACUBED INGESTION PIPELINE STARTED")
    logger.info("=" * 80)

    logger.info("Initializing application context")
    app = ApplicationContext()
    game = app.runtime.game

    logger.info("Environment detected: %s", app.environment)
    logger.info("Selected game: %s (%s)", game.name, game.id)
    logger.info(
        "Catalog: %s",
        getattr(app.storage, "catalog", "N/A"),
    )
    logger.info(
        "Schema: %s",
        getattr(app.storage, "schema", "N/A"),
    )

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

    # =========================================================
    # STEP 1: INGEST
    # =========================================================
    stepfiles = await engine.run()

    logger.info("Ingested %d stepfiles", len(stepfiles))

    # =========================================================
    # STEP 2: TRANSFORM (ETL)
    # =========================================================
    etl = stepfiles_to_tables(stepfiles)

    logger.info(
        "Transformed -> %d charts, %d notes",
        len(etl.charts),
        len(etl.notes),
    )

    # =========================================================
    # STEP 3: LOAD (PERSISTENCE)
    # =========================================================
    storage = app.storage
    table_config = app.table_config

    # songs_repo = SongsRepository(
    #     storage, table_config, logger
    # )

    charts_repo = ChartsRepository(storage, table_config, logger)

    notes_repo = NotesRepository(storage, table_config, logger)

    # Songs sync (if you have song data elsewhere; placeholder here)
    # songs_repo.sync_songlist(...)

    charts_repo.sync_charts(etl.charts)
    notes_repo.sync_notes(etl.notes)

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
        help="Game id to ingest. Defaults to the GAME environment variable.",
    )
    args, _ = parser.parse_known_args()

    try:
        asyncio.get_running_loop()
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run, async_main(game_id=args.game)
            )
            future.result()
    except RuntimeError:
        asyncio.run(async_main(game_id=args.game))


if __name__ == "__main__":
    main()
