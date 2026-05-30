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
        app.tables.silver_events,
    )

    print(train_df)

    _train_df = app.storage.read_table(
        app.tables.silver_songs,
    )

    print(_train_df)


if __name__ == "__main__":
    main()
