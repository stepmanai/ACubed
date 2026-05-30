# cli/ingest.py

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

    logger = get_logger()

    app = ApplicationContext()

    logger.info(
        "Environment: %s",
        app.environment,
    )

    api_key = get_api_key(
        app.environment,
    )

    api_client = FFRClient(
        api_key=api_key,
        base_api_url=config.base_api_url,
        playlist_url=config.playlist_url,
        timeout=config.request_timeout,
        retries=config.max_retries,
        thread_pool_size=config.thread_pool_size,
    )

    dataframe_factory = build_dataframe_factory(
        app.environment,
    )

    service = IngestionService(
        storage=app.storage,
        api_client=api_client,
        table_config=app.tables,
        logger=logger,
        dataframe_factory=dataframe_factory,
    )

    changed_ids = service.sync_songlist()

    service.sync_charts(
        changed_ids,
    )

    service.sync_playlist()

    logger.info("FFR ingestion complete")


if __name__ == "__main__":
    main()
