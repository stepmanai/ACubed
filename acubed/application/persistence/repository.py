from __future__ import annotations

import os
import subprocess
import sys
import time
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


class DatabricksStepfileRepository:
    def __init__(
        self,
        storage,
        table_config,
        logger,
        workers: int,
    ):
        self.storage = storage
        self.table_config = table_config
        self.logger = logger
        self.workers = int(os.getenv("ACUBED_DATABRICKS_WORKERS", workers))

        required_methods = (
            "distributed_stepfiles_to_tables",
            "sync_ingestion_tables",
            "optimize_tables",
        )
        missing = [
            method
            for method in required_methods
            if not hasattr(storage, method)
        ]
        if missing:
            raise TypeError(
                "DatabricksStepfileRepository requires Databricks storage "
                f"methods: {', '.join(missing)}"
            )

    def sync_stepfiles(self, stepfiles) -> dict[str, float]:
        self.logger.info("=" * 80)
        self.logger.info("OPTIMIZED INGESTION PIPELINE - SPARK NATIVE")
        self.logger.info("=" * 80)
        self.logger.info("Workers: %s", self.workers)

        transform_start = time.time()
        frames = self.storage.distributed_stepfiles_to_tables(
            stepfiles,
            self.workers,
        )
        transform_elapsed = time.time() - transform_start

        self.logger.info(
            "Transformed in %.2fs (distributed)",
            transform_elapsed,
        )
        self.logger.info("Charts: %s rows", f"{frames.charts_count:,}")
        self.logger.info("Notes: %s rows", f"{frames.notes_count:,}")

        load_start = time.time()
        try:
            actions = self.storage.sync_ingestion_tables(
                self.table_config,
                frames,
            )
            load_elapsed = time.time() - load_start
            self.logger.info("Loaded tables in %.2fs", load_elapsed)

            for table_name, action in actions.items():
                self.logger.info("%s %s", action.title(), table_name)

            optimize_start = time.time()
            self.logger.info("Optimizing Delta tables")
            self.storage.optimize_tables(
                (self.table_config.charts, self.table_config.notes)
            )
            optimize_elapsed = time.time() - optimize_start
            self.logger.info(
                "Optimization complete in %.2fs",
                optimize_elapsed,
            )
        finally:
            frames.unpersist()

        self.logger.info("=" * 80)
        self.logger.info("DATABRICKS PHASES")
        self.logger.info("  Transform: %.2fs (distributed)", transform_elapsed)
        self.logger.info("  Load:      %.2fs", load_elapsed)
        self.logger.info("  Optimize:  %.2fs", optimize_elapsed)
        self.logger.info("=" * 80)

        return {
            "transform": transform_elapsed,
            "load": load_elapsed,
            "optimize": optimize_elapsed,
        }


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
