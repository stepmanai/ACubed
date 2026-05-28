# ingestion/service.py

import narwhals as nw


class IngestionService:
    def __init__(
        self,
        storage,
        api_client,
        table_config,
        logger,
        dataframe_factory,
    ):
        self.storage = storage
        self.api_client = api_client
        self.table_config = table_config
        self.logger = logger
        self.dataframe_factory = dataframe_factory

    def _frame(self, data):
        native = self.dataframe_factory(data)

        return nw.from_native(
            native,
            eager_only=True,
        )

    def _native_to_frame(
        self,
        native,
    ):
        if hasattr(native, "df"):
            native = native.df()

        return nw.from_native(
            native,
            eager_only=True,
        )

    def _column_to_list(
        self,
        frame,
        column,
    ):
        native = frame.select(column).to_native()

        # pandas
        if hasattr(native, "__getitem__"):
            try:
                return native[column].tolist()
            except Exception:
                pass

        # polars
        if hasattr(native, "to_dicts"):
            return [row[column] for row in native.to_dicts()]

        raise TypeError(f"Unsupported dataframe type: {type(native)}")

    def _row_count(
        self,
        frame,
    ):
        native = frame.select(nw.len()).to_native()

        # pandas
        if hasattr(native, "iloc"):
            return native.iloc[0, 0]

        # polars
        if hasattr(native, "to_dicts"):
            return native.to_dicts()[0].get("len", 0)

        # spark
        if hasattr(native, "collect"):
            return native.collect()[0][0]

        raise TypeError(f"Unsupported dataframe type: {type(native)}")

    def sync_songlist(self):
        songs = self.api_client.fetch_songlist()

        current = self._frame(songs)

        exists = self.storage.table_exists(self.table_config.songlist)

        if not exists:
            self.storage.overwrite_table(
                self.table_config.songlist,
                current.to_native(),
            )

            self.logger.info(
                "Created songlist table with %s rows",
                self._row_count(current),
            )

            return self._column_to_list(
                current,
                "id",
            )

        previous_native = self.storage.read_table(self.table_config.songlist)

        previous = self._native_to_frame(previous_native)

        joined = previous.join(
            current,
            on="id",
            how="inner",
            suffix="_new",
        )

        changed = joined.filter(
            nw.col("swf_version") != nw.col("swf_version_new")
        )

        changed_ids = self._column_to_list(
            changed,
            "id",
        )

        new_songs = current.join(
            previous.select("id"),
            on="id",
            how="anti",
        )

        new_song_ids = self._column_to_list(
            new_songs,
            "id",
        )

        deleted = previous.join(
            current.select("id"),
            on="id",
            how="anti",
        )

        deleted_ids = self._column_to_list(
            deleted,
            "id",
        )

        if deleted_ids:
            self.storage.delete_where_in(
                self.table_config.songlist,
                "id",
                deleted_ids,
            )

            self.storage.delete_where_in(
                self.table_config.charts,
                "song_id",
                deleted_ids,
            )

        all_changed_ids = changed_ids + new_song_ids

        self.storage.upsert_table(
            self.table_config.songlist,
            current.to_native(),
            ["id"],
        )

        self.logger.info(
            "Detected %s changed songs",
            len(all_changed_ids),
        )

        return all_changed_ids

    def sync_charts(
        self,
        song_ids,
    ):
        if not song_ids:
            self.logger.info("No charts to update")
            return

        chart_data = self.api_client.fetch_charts_parallel(song_ids)

        charts = self._frame(chart_data)

        exists = self.storage.table_exists(self.table_config.charts)

        if exists:
            self.storage.upsert_table(
                self.table_config.charts,
                charts.to_native(),
                ["song_id"],
            )
        else:
            self.storage.overwrite_table(
                self.table_config.charts,
                charts.to_native(),
            )

        self.logger.info(
            "Charts synced: %s",
            self._row_count(charts),
        )

    def sync_playlist(self):
        playlist = self.api_client.fetch_playlist()

        playlist_df = self._frame(playlist)

        self.storage.overwrite_table(
            self.table_config.playlist,
            playlist_df.to_native(),
        )

        self.logger.info(
            "Playlist synced: %s",
            self._row_count(playlist_df),
        )
