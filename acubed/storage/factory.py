# storage/factory.py

from acubed.core.runtime import (
    RuntimeContext,
)
from acubed.models.environment import (
    Environment,
)
from acubed.models.registry import (
    GAME_METADATA,
)


def build_storage(
    context: RuntimeContext,
    config,
):
    metadata = GAME_METADATA[context.game]

    if context.environment == Environment.LOCAL:
        from acubed.storage.duckdb import (
            DuckDBStorage,
        )

        return DuckDBStorage(database_path=(metadata.default_database))

    if context.environment in {
        Environment.DATABRICKS,
        Environment.DATABRICKS_SERVERLESS,
    }:
        from pyspark.sql import (
            SparkSession,
        )

        from acubed.storage.databricks import (
            DatabricksStorage,
        )

        spark = SparkSession.builder.getOrCreate()

        return DatabricksStorage(
            spark=spark,
            game=context.game,
        )

    raise ValueError(
        f"""
        Unsupported environment:
        {context.environment}
        """
    )
