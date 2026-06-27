# infrastructure/storage/factory.py

from acubed.infrastructure.environment.types import (
    Environment,
    is_databricks_environment,
)
from acubed.infrastructure.filesystem.paths import DUCKDB_PATH
from acubed.runtime.context import RuntimeContext


def build_storage(
    context: RuntimeContext,
    config,
):
    if context.environment == Environment.LOCAL:
        from acubed.infrastructure.storage.duckdb import DuckDBStorage

        db_path = config.database_path or DUCKDB_PATH

        return DuckDBStorage(
            database_path=db_path,
            catalog=config.catalog,
            schema=config.schema or context.game.id,
        )

    if is_databricks_environment(context.environment):
        from pyspark.sql import SparkSession

        from acubed.infrastructure.storage.databricks import DatabricksStorage

        spark = SparkSession.builder.getOrCreate()

        return DatabricksStorage(
            spark=spark,
            game=context.game,
            catalog=config.catalog,
            schema=config.schema or context.game.id,
        )

    raise ValueError(f"Unsupported environment: {context.environment}")
