# runtime/app.py

from acubed.infrastructure.environment.detection import detect_environment
from acubed.infrastructure.environment.types import Environment
from acubed.infrastructure.filesystem.init import ensure_directories
from acubed.infrastructure.filesystem.paths import DUCKDB_PATH
from acubed.infrastructure.storage.config import StorageConfig
from acubed.infrastructure.storage.factory import build_storage
from acubed.infrastructure.storage.tables import build_table_config
from acubed.plugins.registry import registry
from acubed.runtime.context import RuntimeContext
from acubed.runtime.settings import RuntimeConfig, RuntimeSettings


class ApplicationContext:
    def __init__(self):

        self.environment = detect_environment()

        if self.environment == Environment.LOCAL:
            ensure_directories()

        self.runtime_config = RuntimeConfig()
        self.game = registry.get(self.runtime_config.game)

        self.table_config = build_table_config(self.game.id)

        self.settings = RuntimeSettings(
            runtime=self.runtime_config,
            storage=StorageConfig(
                database_path=(
                    DUCKDB_PATH
                    if self.environment == Environment.LOCAL
                    else None
                ),
                catalog="acubed",
                schema=self.game.id,
            ),
        )

        # 5. runtime context
        self.runtime = RuntimeContext(
            environment=self.environment,
            game=self.game,
            settings=self.settings,
        )

        # 6. storage backend
        self.storage = build_storage(
            context=self.runtime,
            config=self.settings.storage,
        )
