# cli/ingest.py

import time

from acubed.api.ffr import FFRClient
from acubed.config.runtime import (
    config,
)
from acubed.core.bootstrap import (
    ApplicationContext,
)
from acubed.dataframe.factory import (
    build_dataframe_factory,
)
from acubed.environment.secrets import (
    get_api_key,
)
from acubed.ingestion.service import (
    IngestionService,
)
from acubed.logging.factory import (
    get_logger,
)


def main():
    start_time = time.time()

    logger = get_logger()
    logger.info("=" * 80)
    logger.info("FFR INGESTION PIPELINE STARTED")
    logger.info("=" * 80)

    logger.info("Step 1/6: Initializing application context...")
    app = ApplicationContext()
    logger.info("✓ Environment detected: %s", app.environment)
    logger.info(
        "✓ Catalog: %s",
        app.storage.catalog if hasattr(app.storage, "catalog") else "N/A",
    )
    logger.info(
        "✓ Schema: %s",
        app.storage.schema if hasattr(app.storage, "schema") else "N/A",
    )

    logger.info("Step 2/6: Retrieving API credentials...")
    api_key = get_api_key(app.environment)
    logger.info("✓ API key retrieved successfully")

    logger.info("Step 3/6: Initializing FFR API client...")
    logger.info("  - Base API URL: %s", config.base_api_url)
    logger.info("  - Playlist URL: %s", config.playlist_url)
    logger.info("  - Request timeout: %s seconds", config.request_timeout)
    logger.info("  - Max retries: %s", config.max_retries)
    logger.info("  - Thread pool size: %s", config.thread_pool_size)

    api_client = FFRClient(
        api_key=api_key,
        base_api_url=config.base_api_url,
        playlist_url=config.playlist_url,
        timeout=config.request_timeout,
        retries=config.max_retries,
        thread_pool_size=config.thread_pool_size,
    )
    logger.info("✓ API client initialized")

    logger.info(
        "Step 4/6: Building dataframe factory for environment: %s",
        app.environment,
    )
    dataframe_factory = build_dataframe_factory(app.environment)
    logger.info("✓ Dataframe factory created")

    logger.info("Step 5/6: Initializing ingestion service...")
    service = IngestionService(
        storage=app.storage,
        api_client=api_client,
        table_config=app.tables,
        logger=logger,
        dataframe_factory=dataframe_factory,
    )
    logger.info("✓ Ingestion service initialized")

    logger.info("Step 6/6: Running ingestion pipeline...")
    logger.info("-" * 80)

    logger.info("Syncing songlist table...")
    sync_start = time.time()
    changed_ids = service.sync_songlist()
    sync_duration = time.time() - sync_start
    logger.info("✓ Songlist synced in %.2f seconds", sync_duration)
    logger.info("  - Changed song IDs: %d", len(changed_ids))

    logger.info("Syncing charts table...")
    sync_start = time.time()
    service.sync_charts(changed_ids)
    sync_duration = time.time() - sync_start
    logger.info("✓ Charts synced in %.2f seconds", sync_duration)

    logger.info("Syncing playlist table...")
    sync_start = time.time()
    service.sync_playlist()
    sync_duration = time.time() - sync_start
    logger.info("✓ Playlist synced in %.2f seconds", sync_duration)

    total_duration = time.time() - start_time
    logger.info("-" * 80)
    logger.info("=" * 80)
    logger.info("FFR INGESTION PIPELINE COMPLETED SUCCESSFULLY")
    logger.info(
        "Total execution time: %.2f seconds (%.2f minutes)",
        total_duration,
        total_duration / 60,
    )
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
