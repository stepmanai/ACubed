# cli/features.py

from acubed.core.bootstrap import (
    ApplicationContext,
)
from acubed.features.executors.materialization import (
    FeatureExecutor,
)


def main():

    app = ApplicationContext()

    executor = FeatureExecutor(
        context=app.runtime,
        storage=app.storage,
        tables=app.tables,
    )

    executor.materialize()


if __name__ == "__main__":
    main()
