# core/bootstrap.py

from acubed.config.runtime import config
from acubed.config.tables import build_table_config
from acubed.core.runtime import RuntimeContext
from acubed.core.runtime_bootstrap import (
    bootstrap_runtime,
)
from acubed.environment.detection import detect_environment
from acubed.storage.factory import build_storage


class ApplicationContext:
    def __init__(self):

        self.environment = detect_environment()

        self.runtime = RuntimeContext(
            environment=self.environment,
            game=config.game,
        )

        bootstrap_runtime(
            self.runtime.environment,
        )

        self.storage = build_storage(
            context=self.runtime,
            config=config,
        )

        self.tables = build_table_config(
            game=self.runtime.game,
            catalog="acubed",
        )
