import os

from acubed.infrastructure.environment.types import Environment
from acubed.infrastructure.filesystem.paths import DUCKDB_PATH
from acubed.infrastructure.storage.config import StorageConfig
from acubed.runtime.settings import RuntimeConfig, RuntimeSettings


def build_runtime_config(game_override: str | None = None) -> RuntimeConfig:
    return RuntimeConfig(
        game=game_override or os.getenv("GAME", "ffr"),
        thread_pool_size=int(os.getenv("THREAD_POOL_SIZE", 4)),
        request_timeout=int(os.getenv("REQUEST_TIMEOUT", 10)),
        max_retries=int(os.getenv("MAX_RETRIES", 5)),
    )


def build_runtime_settings(
    game_override: str | None = None,
    environment: Environment | None = None,
    game=None,
) -> RuntimeSettings:

    runtime = build_runtime_config(game_override)

    return RuntimeSettings(
        runtime=build_runtime_config(game_override),
        storage=StorageConfig(
            database_path=(
                DUCKDB_PATH if environment == Environment.LOCAL else None
            ),
            catalog="acubed",
            schema=runtime.game,
        ),
    )
