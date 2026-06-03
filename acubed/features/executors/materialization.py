# features/executors/materialization.py

import subprocess
import sys

from acubed.config.tables import TableConfig
from acubed.core.runtime import RuntimeContext
from acubed.features.materialization.gold_layer import (
    build_gold_note_features,
    build_gold_targets,
)
from acubed.features.materialization.silver_layer import (
    build_silver_events,
)
from acubed.storage.base import BaseStorage

try:
    import narwhals as nw
except ImportError:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "narwhals"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    import narwhals as nw


class FeatureExecutor:
    def __init__(
        self,
        context: RuntimeContext,
        storage: BaseStorage,
        tables: TableConfig,
    ):
        self.context = context
        self.storage = storage
        self.tables = tables

    def materialize_silver(self):

        bronze_charts_df = self.storage.read_table(self.tables.charts)

        silver_events_df = nw.to_native(
            build_silver_events(nw.from_native(bronze_charts_df))
        )

        self.storage.overwrite_table(
            self.tables.silver_events,
            silver_events_df,
        )

    def materialize_gold(self):

        bronze_playlist_df = self.storage.read_table(self.tables.playlist)

        gold_targets_df = nw.to_native(
            build_gold_targets(nw.from_native(bronze_playlist_df))
        )

        silver_events_spark_df = self.storage.read_table(
            self.tables.silver_events
        )

        is_spark = False

        if is_spark:
            gold_note_features_spark_df = build_gold_note_features(
                silver_events_spark_df, use_spark=True
            )

            self.storage.overwrite_table(
                self.tables.gold_features,
                gold_note_features_spark_df,
            )
        else:
            event_rows = self.storage.iter_event_rows(
                self.tables.silver_events
            )

            gold_note_features_df = nw.to_native(
                nw.from_dicts(
                    build_gold_note_features(event_rows, use_spark=False),
                    backend="pandas",
                )
            )

            self.storage.overwrite_table(
                self.tables.gold_features,
                gold_note_features_df,
            )

        self.storage.overwrite_table(
            self.tables.gold_targets,
            gold_targets_df,
        )

    def materialize(self):

        self.materialize_silver()

        self.materialize_gold()
