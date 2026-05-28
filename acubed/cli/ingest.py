# cli/ingest.py

from acubed.api.ffr import FFRClient
from acubed.config.runtime import (
    config,
)
from acubed.config.tables import (
    build_table_config,
)
from acubed.core.runtime import (
    RuntimeContext,
)
from acubed.dataframe.factory import (
    build_dataframe_factory,
)
from acubed.environment.detection import (
    detect_environment,
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
from acubed.storage.factory import (
    build_storage,
)


def main():
    logger = get_logger()

    environment = detect_environment()

    logger.info(
        "Environment: %s",
        environment,
    )

    context = RuntimeContext(
        environment=environment,
        game=config.game,
    )

    api_key = get_api_key(
        environment,
    )

    api_client = FFRClient(
        api_key=api_key,
        base_api_url=config.base_api_url,
        playlist_url=config.playlist_url,
        timeout=config.request_timeout,
        retries=config.max_retries,
        thread_pool_size=(config.thread_pool_size),
    )

    storage = build_storage(
        context=context,
        config=config,
    )

    dataframe_factory = build_dataframe_factory(environment)

    table_config = build_table_config(
        game=context.game,
        catalog="acubed",
    )

    service = IngestionService(
        storage=storage,
        api_client=api_client,
        table_config=table_config,
        logger=logger,
        dataframe_factory=(dataframe_factory),
    )

    changed_ids = service.sync_songlist()

    service.sync_charts(changed_ids)

    service.sync_playlist()

    logger.info("FFR ingestion complete")


if __name__ == "__main__":
    main()
