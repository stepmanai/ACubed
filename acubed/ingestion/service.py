# ingestion/service.py

import pandas as pd


class IngestionService:
    def __init__(
        self,
        storage,
        api_client,
        table_config,
        logger,
    ):
        self.storage = storage
        self.api_client = api_client
        self.table_config = table_config
        self.logger = logger

    def sync_songlist(self):
        songs = self.api_client.fetch_songlist()

        df = pd.DataFrame(songs)

        exists = self.storage.table_exists(self.table_config.songlist)

        if not exists:
            self.storage.overwrite_table(self.table_config.songlist, df)

            self.logger.info("Created songlist table with %s rows", len(df))

            return df["id"].tolist()

        previous = self.storage.read_table(self.table_config.songlist).toPandas()

        changed = pd.merge(
            previous, df, on="id", suffixes=("_old", "_new"), how="inner"
        )

        changed = changed[
            changed["swf_version_old"] != changed["swf_version_new"]
        ]

        new_songs = df[~df["id"].isin(previous["id"])]

        deleted = previous[~previous["id"].isin(df["id"])]

        deleted_ids = deleted["id"].tolist()

        if deleted_ids:
            self.storage.delete_where_in(
                self.table_config.songlist, "id", deleted_ids
            )

            self.storage.delete_where_in(
                self.table_config.charts, "song_id", deleted_ids
            )

        changed_ids = changed["id"].tolist() + new_songs["id"].tolist()

        self.storage.upsert_table(self.table_config.songlist, df, ["id"])

        self.logger.info("Detected %s changed songs", len(changed_ids))

        return changed_ids

    def sync_charts(
        self,
        song_ids,
    ):
        if not song_ids:
            self.logger.info("No charts to update")
            return

        chart_data = self.api_client.fetch_charts_parallel(song_ids)

        chart_df = pd.DataFrame(chart_data)

        exists = self.storage.table_exists(self.table_config.charts)

        if exists:
            self.storage.upsert_table(
                self.table_config.charts, chart_df, ["song_id"]
            )
        else:
            self.storage.overwrite_table(self.table_config.charts, chart_df)

        self.logger.info("Charts synced: %s", len(chart_df))

    def sync_playlist(self):
        playlist = self.api_client.fetch_playlist()

        playlist_df = pd.DataFrame(playlist)

        self.storage.overwrite_table(self.table_config.playlist, playlist_df)

        self.logger.info("Playlist synced: %s", len(playlist_df))
