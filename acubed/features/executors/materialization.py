import narwhals as nw

from acubed.config.tables import TableConfig
from acubed.features.materialization.gold_layer import (
    build_gold_features,
)
from acubed.features.materialization.silver_layer import (
    build_silver_events,
    build_silver_songs,
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

        bronze_charts_df = self.storage.read_table(self.tables.charts)
        bronze_playlist_df = self.storage.read_table(self.tables.playlists)

        silver_events_df = nw.to_native(
            build_silver_events(nw.from_native(bronze_charts_df))
        )

        silver_songs_df = nw.to_native(
            build_silver_songs(nw.from_native(bronze_playlist_df))
        )

        self.storage.overwrite_table(
            self.tables.silver_events,
            silver_events_df,
        )

        self.storage.overwrite_table(
            self.tables.silver_songs,
            silver_songs_df,
        )

    def materialize_gold(self):

        bronze_df = self.storage.read_table(self.tables.charts)

        gold_df = nw.to_native(build_gold_features(nw.from_native(bronze_df)))

        self.storage.overwrite_table(
            self.tables.gold_features,
            gold_df,
        )

    def materialize(self):

        self.materialize_silver()

        # self.materialize_gold()
