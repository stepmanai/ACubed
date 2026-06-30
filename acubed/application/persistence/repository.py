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


class BronzeRepository(_BaseRepository):
    def _columns_for_table(self, table_name: str):
        table = self.storage.read_table(table_name)
        columns = getattr(table, "columns", None)
        if columns is not None:
            return set(columns)
        schema = getattr(table, "schema", None)
        if schema is not None and hasattr(schema, "names"):
            return set(schema.names)
        return set()

    def sync_rows(
        self,
        table_name: str,
        rows: list[dict],
        key_columns: list[str],
        label: str,
    ):
        if not rows:
            self.logger.info("No %s to sync", label)
            return

        rows = self._dedupe_rows(rows, key_columns)
        frame = self._frame(rows)
        exists = self.storage.table_exists(table_name)
        table_columns = (
            self._columns_for_table(table_name) if exists else set()
        )
        row_columns = set(rows[0])

        if (
            exists
            and set(key_columns).issubset(table_columns)
            and table_columns == row_columns
        ):
            self.storage.upsert_table(
                table_name,
                frame.to_native(),
                key_columns,
            )
        else:
            self.storage.overwrite_table(
                table_name,
                frame.to_native(),
            )

        self.logger.info("%s synced: %s rows", label, self._row_count(frame))

    def _dedupe_rows(
        self,
        rows: list[dict],
        key_columns: list[str],
    ) -> list[dict]:
        deduped = {}
        for row in rows:
            key = tuple(row.get(column) for column in key_columns)
            deduped[key] = row

        return list(deduped.values())

    def sync_collections(self, collections: list[dict]):
        self.sync_rows(
            self.table_config.collections,
            collections,
            ["_acubed_collection_id"],
            "Collections",
        )

    def sync_charts(self, charts: list[dict]):
        self.sync_rows(
            self.table_config.charts,
            charts,
            ["_acubed_chart_id"],
            "Charts",
        )

    def sync_source(self, source: list[dict]):
        self.sync_rows(
            self.table_config.source,
            source,
            ["_acubed_source_id"],
            "Source",
        )


class ChartsRepository(BronzeRepository):
    pass


# Silver writes are disabled while bronze chart tables are being built.
# class NotesRepository(_BaseRepository):
#     def sync_notes(self, notes: list[dict]):
#         if not notes:
#             self.logger.info("No notes to sync")
#             return
#
#         frame = self._frame(notes)
#
#         exists = self.storage.table_exists(self.table_config.notes)
#
#         if exists:
#             self.storage.upsert_table(
#                 self.table_config.notes,
#                 frame.to_native(),
#                 ["song_id", "note_id"],
#             )
#         else:
#             self.storage.overwrite_table(
#                 self.table_config.notes,
#                 frame.to_native(),
#             )
#
#         self.logger.info("Notes synced: %s rows", self._row_count(frame))


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
            # "distributed_api_assets_to_bronze_tables",
            # Parsing is disabled while bronze chart tables are being built.
            # "distributed_stepfiles_to_tables",
            "sync_delta_table",
            # "sync_ingestion_tables",
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

    def sync_bronze_tables(
        self,
        collections: list[dict],
        charts: list[dict],
        source: list[dict],
        optimize: bool = True,
    ) -> None:
        if collections:
            collections = self._dedupe_rows(
                collections,
                ["_acubed_collection_id"],
            )
            self.storage.sync_delta_table(
                self.table_config.collections,
                collections,
                key_columns=("_acubed_collection_id",),
            )
            self.logger.info("Collections synced: %s rows", len(collections))

        if charts:
            charts = self._dedupe_rows(charts, ["_acubed_chart_id"])
            self.storage.sync_delta_table(
                self.table_config.charts,
                charts,
                key_columns=("_acubed_chart_id",),
            )
            self.logger.info("Charts synced: %s rows", len(charts))

        if source:
            source = self._dedupe_rows(source, ["_acubed_source_id"])
            self.storage.sync_delta_table(
                self.table_config.source,
                source,
                key_columns=("_acubed_source_id",),
            )
            self.logger.info("Source synced: %s rows", len(source))

        if optimize:
            self.storage.optimize_tables(
                (
                    self.table_config.collections,
                    self.table_config.charts,
                    self.table_config.source,
                )
            )

    def _dedupe_rows(
        self,
        rows: list[dict],
        key_columns: list[str],
    ) -> list[dict]:
        deduped = {}
        for row in rows:
            key = tuple(row.get(column) for column in key_columns)
            deduped[key] = row

        return list(deduped.values())

    def sync_assets(
        self,
        assets,
        optimize: bool = True,
    ) -> dict[str, float]:
        self.logger.info("=" * 80)
        self.logger.info("BRONZE API INGESTION PIPELINE - SPARK NATIVE")
        self.logger.info("=" * 80)
        self.logger.info("Workers: %s", self.workers)

        transform_start = time.time()
        frames = self.storage.distributed_api_assets_to_bronze_tables(
            assets,
            self.workers,
        )
        transform_elapsed = time.time() - transform_start

        self.logger.info(
            "Transformed API assets in %.2fs (distributed)",
            transform_elapsed,
        )
        self.logger.info("Bronze charts: %s rows", f"{frames.charts_count:,}")

        load_start = time.time()
        try:
            actions = {
                self.table_config.charts: self.storage.sync_delta_table(
                    self.table_config.charts,
                    frames.charts,
                    key_columns=("_acubed_chart_id",),
                )
            }
            if frames.source is not None:
                actions[self.table_config.source] = (
                    self.storage.sync_delta_table(
                        self.table_config.source,
                        frames.source,
                        key_columns=("_acubed_source_id",),
                    )
                )
            load_elapsed = time.time() - load_start
            self.logger.info("Loaded tables in %.2fs", load_elapsed)

            for table_name, action in actions.items():
                self.logger.info("%s %s", action.title(), table_name)

            optimize_elapsed = 0.0
            if optimize:
                optimize_start = time.time()
                self.logger.info("Optimizing bronze Delta tables")
                self.storage.optimize_tables(
                    (self.table_config.charts, self.table_config.source)
                )
                optimize_elapsed = time.time() - optimize_start
                self.logger.info(
                    "Optimization complete in %.2fs",
                    optimize_elapsed,
                )
        finally:
            frames.unpersist()

        self.logger.info("=" * 80)
        self.logger.info("DATABRICKS BRONZE PHASES")
        self.logger.info("  Transform: %.2fs (distributed)", transform_elapsed)
        self.logger.info("  Load:      %.2fs", load_elapsed)
        self.logger.info("  Optimize:  %.2fs", optimize_elapsed)
        self.logger.info("=" * 80)

        return {
            "transform": transform_elapsed,
            "load": load_elapsed,
            "optimize": optimize_elapsed,
        }

    # API parsing is disabled while bronze chart tables are being built.
    # def sync_stepfiles(self, stepfiles) -> dict[str, float]:
    #     self.logger.info("=" * 80)
    #     self.logger.info("OPTIMIZED INGESTION PIPELINE - SPARK NATIVE")
    #     self.logger.info("=" * 80)
    #     self.logger.info("Workers: %s", self.workers)
    #
    #     transform_start = time.time()
    #     frames = self.storage.distributed_stepfiles_to_tables(
    #         stepfiles,
    #         self.workers,
    #     )
    #     transform_elapsed = time.time() - transform_start
    #
    #     self.logger.info(
    #         "Transformed in %.2fs (distributed)",
    #         transform_elapsed,
    #     )
    #     self.logger.info("Charts: %s rows", f"{frames.charts_count:,}")
    #     self.logger.info("Notes: %s rows", f"{frames.notes_count:,}")
    #
    #     load_start = time.time()
    #     try:
    #         actions = self.storage.sync_ingestion_tables(
    #             self.table_config,
    #             frames,
    #         )
    #         load_elapsed = time.time() - load_start
    #         self.logger.info("Loaded tables in %.2fs", load_elapsed)
    #
    #         for table_name, action in actions.items():
    #             self.logger.info("%s %s", action.title(), table_name)
    #
    #         optimize_start = time.time()
    #         self.logger.info("Optimizing Delta tables")
    #         self.storage.optimize_tables(
    #             (
    #                 self.table_config.charts,
    #                 # Silver optimization is disabled while bronze chart
    #                 # tables are being built.
    #                 # self.table_config.notes,
    #             )
    #         )
    #         optimize_elapsed = time.time() - optimize_start
    #         self.logger.info(
    #             "Optimization complete in %.2fs",
    #             optimize_elapsed,
    #         )
    #     finally:
    #         frames.unpersist()
    #
    #     self.logger.info("=" * 80)
    #     self.logger.info("DATABRICKS PHASES")
    #     self.logger.info("  Transform: %.2fs (distributed)",
    #         transform_elapsed)
    #     self.logger.info("  Load:      %.2fs", load_elapsed)
    #     self.logger.info("  Optimize:  %.2fs", optimize_elapsed)
    #     self.logger.info("=" * 80)
    #
    #     return {
    #         "transform": transform_elapsed,
    #         "load": load_elapsed,
    #         "optimize": optimize_elapsed,
    #     }


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
