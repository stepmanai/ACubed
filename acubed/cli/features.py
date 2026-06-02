# cli/features.py

import subprocess
import sys

from acubed.core.bootstrap import (
    ApplicationContext,
)
from acubed.features.executors.materialization import (
    FeatureExecutor,
)
from acubed.models.environment import (
    Environment,
)


def main():

    app = ApplicationContext()

    if app.runtime.environment == Environment.DATABRICKS_SERVERLESS:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q", "narwhals"]
        )

    executor = FeatureExecutor(
        context=app.runtime,
        storage=app.storage,
        tables=app.tables,
    )

    executor.materialize()


if __name__ == "__main__":
    main()
