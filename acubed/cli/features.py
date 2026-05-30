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
        storage=app.storage,
        tables=app.tables,
    )

    executor.materialize()

    train_df = app.storage.read_table(
        app.tables.gold_features,
    )

    print(train_df)


if __name__ == "__main__":
    main()
