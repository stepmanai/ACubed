from __future__ import annotations

import os

from acubed.infrastructure.environment.types import (
    Environment,
    is_databricks_environment,
)
from acubed.infrastructure.filesystem.paths import DUCKDB_PATH
from acubed.infrastructure.storage.config import StorageConfig
from acubed.runtime.settings import RuntimeConfig, RuntimeSettings


def build_runtime_config(
    game_override: str | None = None,
    environment: Environment | None = None,
) -> RuntimeConfig:
    """Build runtime configuration with environment-aware defaults.

    Databricks Serverless benefits from higher parallelism (16 workers),
    while local development uses lower parallelism (4 workers).
    """
    # Auto-detect optimal thread pool size based on environment
    # Databricks: 16 workers (4x increase for serverless auto-scaling)
    # Local: 4 workers (lower resource usage for development)
    default_workers = (
        16 if environment and is_databricks_environment(environment) else 4
    )

    return RuntimeConfig(
        game=game_override or os.getenv("GAME", "ffr"),
        thread_pool_size=int(os.getenv("THREAD_POOL_SIZE", default_workers)),
        request_timeout=int(os.getenv("REQUEST_TIMEOUT", 10)),
        max_retries=int(os.getenv("MAX_RETRIES", 5)),
    )


def build_runtime_settings(
    game_override: str | None = None,
    environment: Environment | None = None,
    game=None,
) -> RuntimeSettings:

    runtime = build_runtime_config(game_override, environment)

    return RuntimeSettings(
        runtime=runtime,
        storage=StorageConfig(
            database_path=(
                DUCKDB_PATH if environment == Environment.LOCAL else None
            ),
            catalog="acubed",
            schema=runtime.game,
        ),
    )
