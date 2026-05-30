from acubed.config.tables import TableConfig
from acubed.features.materialization.gold_features import (
    build_gold_features,
)
from acubed.features.materialization.silver_events import (
    build_silver_events,
)
from acubed.storage.base import BaseStorage


class FeatureExecutor:
    def __init__(
        self,
        storage: BaseStorage,
        tables: TableConfig,
    ):
        self.storage = storage
        self.tables = tables

    def materialize_silver(self):

        bronze_df = self.storage.read_table(self.tables.charts)

        silver_df = build_silver_events(bronze_df)

        self.storage.overwrite_table(
            self.tables.silver_events,
            silver_df,
        )

    def materialize_gold(self):

        bronze_df = self.storage.read_table(self.tables.charts)

        gold_df = build_gold_features(bronze_df)

        self.storage.overwrite_table(
            self.tables.gold_features,
            gold_df,
        )

    def materialize(self):

        self.materialize_silver()

        self.materialize_gold()
