# runtime/app.py

from __future__ import annotations

from acubed.infrastructure.environment.detection import detect_environment
from acubed.infrastructure.environment.types import Environment
from acubed.infrastructure.filesystem.init import ensure_directories
from acubed.infrastructure.storage.factory import build_storage
from acubed.infrastructure.storage.tables import build_table_config
from acubed.plugins.registry import registry
from acubed.runtime.bootstrap import build_runtime_settings
from acubed.runtime.context import RuntimeContext


class ApplicationContext:
    def __init__(self, game_override: str | None = None):

        # 1. environment first
        self.environment = detect_environment()

        if self.environment == Environment.LOCAL:
            ensure_directories()

        # 2. build settings (ONLY depends on env + override)
        self.settings = build_runtime_settings(
            game_override=game_override,
            environment=self.environment,
        )

        # 3. derive game from settings
        self.game = registry.get(self.settings.runtime.game)

        # 4. table config depends on game
        self.table_config = build_table_config(self.game.id)

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
