from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

import pandas as pd

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


# =========================================================
# ETL TRANSFORMER (Stepfile -> relational tables)
# =========================================================


@dataclass
class ChartRow:
    song_id: int
    difficulty: float
    note_count: int


@dataclass
class NoteRow:
    song_id: int
    note_id: int
    timestamp_ms: float
    lane: int
    hold_duration: float


# =========================================================
# BASE REPOSITORY
# =========================================================


class _BaseRepository:
    def __init__(self, storage, table_config, logger):
        self.storage = storage
        self.table_config = table_config
        self.logger = logger

    def _normalize_numeric_types(self, data):
        if not data or not isinstance(data, list):
            return data

        columns_with_numbers = {}

        for row in data:
            for key, value in row.items():
                if isinstance(value, (int, float)) and value is not None:
                    columns_with_numbers.setdefault(
                        key, {"has_int": False, "has_float": False}
                    )

                    if isinstance(value, float):
                        columns_with_numbers[key]["has_float"] = True
                    elif isinstance(value, int):
                        columns_with_numbers[key]["has_int"] = True

        mixed_columns = {
            col
            for col, t in columns_with_numbers.items()
            if t["has_int"] and t["has_float"]
        }

        if not mixed_columns:
            return data

        normalized = []
        for row in data:
            new_row = row.copy()
            for col in mixed_columns:
                if col in new_row and isinstance(new_row[col], int):
                    new_row[col] = float(new_row[col])
            normalized.append(new_row)

        return normalized

    def _frame(self, data):
        data = self._normalize_numeric_types(data)

        # standardize everything to pandas first
        pdf = pd.DataFrame(data)

        return nw.from_native(pdf)

    def _row_count(self, frame):
        native = frame.select(nw.len()).to_native()

        if hasattr(native, "iloc"):
            return native.iloc[0, 0]
        if hasattr(native, "to_dicts"):
            return native.to_dicts()[0].get("len", 0)
        if hasattr(native, "collect"):
            return native.collect()[0][0]

        raise TypeError(f"Unsupported dataframe type: {type(native)}")


# # =========================================================
# # SONGS REPOSITORY (unchanged logic, cleaned typing)
# # =========================================================

# class SongsRepository(_BaseRepository):
#     def sync_songlist(self, songs: list[dict]):
#         current = self._frame(songs)

#         exists = self.storage.table_exists(self.table_config.songlist)

#         if not exists:
#             self.storage.overwrite_table(
#                 self.table_config.songlist,
#                 current.to_native(),
#             )

#             self.logger.info(
#                 "Created songlist table with %s rows",
#                 self._row_count(current),
#             )

#             return

#         self.storage.upsert_table(
#             self.table_config.songlist,
#             current.to_native(),
#             ["id"],
#         )

#         self.logger.info("Songlist synced: %s row", self._row_count(current))


# =========================================================
# CHARTS REPOSITORY (NOW REAL CHART TABLE ONLY)
# =========================================================


class ChartsRepository(_BaseRepository):
    def sync_charts(self, charts: list[dict]):
        if not charts:
            self.logger.info("No charts to sync")
            return

        frame = self._frame(charts)

        exists = self.storage.table_exists(self.table_config.charts)

        if exists:
            self.storage.upsert_table(
                self.table_config.charts,
                frame.to_native(),
                ["song_id"],
            )
        else:
            self.storage.overwrite_table(
                self.table_config.charts,
                frame.to_native(),
            )

        self.logger.info("Charts synced: %s rows", self._row_count(frame))


# =========================================================
# NOTES REPOSITORY (NEW — this is what you were missing)
# =========================================================


class NotesRepository(_BaseRepository):
    def sync_notes(self, notes: list[dict]):
        if not notes:
            self.logger.info("No notes to sync")
            return

        frame = self._frame(notes)

        exists = self.storage.table_exists(self.table_config.notes)

        if exists:
            self.storage.upsert_table(
                self.table_config.notes,
                frame.to_native(),
                ["song_id", "note_id"],
            )
        else:
            self.storage.overwrite_table(
                self.table_config.notes,
                frame.to_native(),
            )

        self.logger.info("Notes synced: %s rows", self._row_count(frame))


# # =========================================================
# # PACKS REPOSITORY (unchanged)
# # =========================================================

# class PacksRepository(_BaseRepository):
#     def sync_playlist(self, playlist: list[dict]):
#         frame = self._frame(playlist)

#         self.storage.overwrite_table(
#             self.table_config.playlist,
#             frame.to_native(),
#         )

#         self.logger.info(
#             "Playlist synced: %s",
#             self._row_count(frame),
#         )
