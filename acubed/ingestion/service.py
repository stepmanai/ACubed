# ingestion/service.py

import subprocess
import sys

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

    def _normalize_numeric_types(self, data):

        if not data or not isinstance(data, list):
            return data

        columns_with_numbers = {}
        for row in data:
            for key, value in row.items():
                if isinstance(value, (int, float)) and value is not None:
                    if key not in columns_with_numbers:
                        columns_with_numbers[key] = {
                            "has_int": False,
                            "has_float": False,
                        }
                    if isinstance(value, float):
                        columns_with_numbers[key]["has_float"] = True
                    elif isinstance(value, int):
                        columns_with_numbers[key]["has_int"] = True

        mixed_columns = {
            col
            for col, types in columns_with_numbers.items()
            if types["has_int"] and types["has_float"]
        }

        if not mixed_columns:
            return data

        normalized_data = []
        for row in data:
            normalized_row = row.copy()
            for col in mixed_columns:
                if col in normalized_row and isinstance(
                    normalized_row[col], int
                ):
                    normalized_row[col] = float(normalized_row[col])
            normalized_data.append(normalized_row)

        return normalized_data

    def _frame(self, data):
        normalized_data = self._normalize_numeric_types(data)
        native = self.dataframe_factory(normalized_data)

        return nw.from_native(native)

    def _native_to_frame(
        self,
        native,
    ):
        if hasattr(native, "df"):
            native = native.df()

        return nw.from_native(native)

    def _column_to_list(
        self,
        frame,
        column,
    ):
        native = frame.select(column).to_native()

        if hasattr(native, "__getitem__"):
            try:
                return native[column].tolist()
            except Exception:
                pass

        if hasattr(native, "to_dicts"):
            return [row[column] for row in native.to_dicts()]

        if hasattr(native, "collect"):
            return [row[0] for row in native.collect()]

        raise TypeError(f"Unsupported dataframe type: {type(native)}")

    def _row_count(
        self,
        frame,
    ):
        native = frame.select(nw.len()).to_native()

        if hasattr(native, "iloc"):
            return native.iloc[0, 0]

        if hasattr(native, "to_dicts"):
            return native.to_dicts()[0].get("len", 0)

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
