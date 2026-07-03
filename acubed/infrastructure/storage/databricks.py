"""Databricks storage adapter.

This module intentionally relies on the Spark session provided by Databricks.
Do not add pyspark, databricks-connect, or delta-spark as project dependencies;
serverless Databricks environments provide the Spark client runtime.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from acubed.domain.chart.types import AssetResponse, ChartRef
from acubed.domain.game.definition import GameDefinition
from acubed.infrastructure.storage.base import BaseStorage
from acubed.utils import api_assets_to_bronze_tables

# API parsing is disabled while bronze chart tables are being built.
# def _stepfile_to_tables(stepfile: Stepfile):
#     try:
#         etl = stepfiles_to_tables([stepfile])
#         return [(etl.charts, etl.notes)]
#     except Exception:
#         return []


def _api_asset_to_bronze(asset: tuple[ChartRef, AssetResponse]):
    try:
        etl = api_assets_to_bronze_tables([asset])
        return etl.charts
    except Exception:
        return []


def _api_asset_to_bronze_source(asset: tuple[ChartRef, AssetResponse]):
    try:
        etl = api_assets_to_bronze_tables([asset])
        return etl.source
    except Exception:
        return []


# API parsing is disabled while bronze chart tables are being built.
# def _extract_charts(tables):
#     charts, _ = tables
#     return charts
#
#
# def _extract_notes(tables):
#     _, notes = tables
#     return notes


@dataclass
class DatabricksTableFrames:
    charts: Any
    source: Any
    charts_count: int
    source_count: int
    _cached_frames: tuple[Any, ...]

    def unpersist(self) -> None:
        for frame in self._cached_frames:
            if hasattr(frame, "unpersist"):
                frame.unpersist()


class DatabricksStorage(BaseStorage):
    def __init__(
        self,
        spark,
        game: GameDefinition,
        catalog: str | None = None,
        schema: str | None = None,
    ):
        self.spark = spark

        self._catalog = catalog
        self._schema = schema or game.id

        self._ensure_namespace()

    @property
    def catalog(self) -> str | None:
        return self._catalog

    @property
    def schema(self) -> str:
        return self._schema

    @property
    def namespace(self) -> str:
        if self.catalog:
            return f"`{self.catalog}`.`{self.schema}`"

        return f"`{self.schema}`"

    def _ensure_namespace(self) -> None:
        self.spark.sql(f"CREATE SCHEMA IF NOT EXISTS {self.namespace}")

    def _get_qualified_name(self, table_name: str) -> str:
        parts = table_name.split(".")
        if len(parts) == 3:
            catalog, schema, table = parts
            return f"`{catalog}`.`{schema}`.`{table}`"

        if len(parts) == 2:
            schema, table = parts
            if self.catalog:
                return f"`{self.catalog}`.`{schema}`.`{table}`"
            return f"`{schema}`.`{table}`"

        return f"{self.namespace}.`{table_name}`"

    def _get_column_types(self):
        """Get the type mappings for all known columns."""
        from pyspark.sql.types import (
            DoubleType,
            LongType,
            StringType,
        )

        return {
            "song_id": LongType(),
            "note_id": LongType(),
            "note_count": LongType(),
            "timestamp_ms": DoubleType(),
            "lane": LongType(),
            "hold_duration": DoubleType(),
            "difficulty": DoubleType(),
            "_acubed_chart_id": StringType(),
            "_acubed_song_id": StringType(),
            "_acubed_collection_id": StringType(),
            "_acubed_source_id": StringType(),
            "api_payload": StringType(),
            "chart_title": StringType(),
            "chart_artist": StringType(),
            "chart_base64": StringType(),
            "difficulty_name": StringType(),
            "keys": LongType(),
            "collection_name": StringType(),
        }

    def _ensure_spark_dataframe(self, dataframe):
        if hasattr(dataframe, "write"):
            return dataframe

        # Extract columns from pandas DataFrame
        if hasattr(dataframe, "columns"):
            columns = list(dataframe.columns)
        else:
            # Fallback for list of dicts
            if isinstance(dataframe, list) and dataframe:
                columns = list(dataframe[0].keys())
            else:
                # Empty or unrecognized type - let Spark infer
                return self.spark.createDataFrame(dataframe)

        # Build explicit schema using known types
        from pyspark.sql.types import (
            StringType,
            StructField,
            StructType,
        )

        column_types = self._get_column_types()
        schema = StructType(
            [
                StructField(
                    col,
                    column_types.get(
                        col, StringType()
                    ),  # Default to StringType for unknown columns
                    True,  # nullable
                )
                for col in columns
            ]
        )

        return self.spark.createDataFrame(dataframe, schema=schema)

    def _empty_dataframe(self, columns: Sequence[str]):
        from pyspark.sql.types import (
            StructField,
            StructType,
        )

        column_types = self._get_column_types()

        return self.spark.createDataFrame(
            [],
            StructType(
                [
                    StructField(column, column_types[column], True)
                    for column in columns
                ]
            ),
        )

    def _dataframe_from_rdd(self, rdd, columns: Sequence[str]):
        if rdd.isEmpty():
            return self._empty_dataframe(columns)

        return self.spark.createDataFrame(rdd)

    # API parsing is disabled while bronze chart tables are being built.
    # def distributed_stepfiles_to_tables(
    #     self,
    #     stepfiles: Sequence[Stepfile],
    #     workers: int,
    # ) -> DatabricksTableFrames:
    #     if not stepfiles:
    #         charts = self._empty_dataframe(
    #             ("_acubed_chart_id", "api_payload")
    #         )
    #         notes = self._empty_dataframe(
    #             (
    #                 "song_id",
    #                 "note_id",
    #                 "timestamp_ms",
    #                 "lane",
    #                 "hold_duration",
    #             )
    #         )
    #         return DatabricksTableFrames(
    #             charts=charts,
    #             notes=notes,
    #             charts_count=0,
    #             notes_count=0,
    #             _cached_frames=(),
    #         )
    #
    #     stepfiles_rdd = self.spark.sparkContext.parallelize(
    #         stepfiles,
    #         numSlices=max(workers, 1),
    #     )
    #     tables_rdd = stepfiles_rdd.flatMap(_stepfile_to_tables).cache()
    #     charts_rdd = tables_rdd.flatMap(_extract_charts)
    #     notes_rdd = tables_rdd.flatMap(_extract_notes)
    #
    #     charts = self._dataframe_from_rdd(
    #         charts_rdd,
    #         ("_acubed_chart_id", "api_payload"),
    #     ).cache()
    #     notes = self._dataframe_from_rdd(
    #         notes_rdd,
    #         (
    #             "song_id",
    #             "note_id",
    #             "timestamp_ms",
    #             "lane",
    #             "hold_duration",
    #         ),
    #     ).cache()
    #
    #     return DatabricksTableFrames(
    #         charts=charts,
    #         notes=notes,
    #         charts_count=charts.count(),
    #         notes_count=notes.count(),
    #         _cached_frames=(charts, notes, tables_rdd),
    #     )

    def distributed_api_assets_to_bronze_tables(
        self,
        assets: Sequence[tuple[ChartRef, AssetResponse]],
        workers: int,
    ) -> DatabricksTableFrames:
        if not assets:
            charts = self._empty_dataframe(
                (
                    "_acubed_chart_id",
                    "_acubed_song_id",
                    "_acubed_collection_id",
                    "chart_title",
                    "chart_artist",
                    "difficulty_name",
                    "difficulty",
                    "keys",
                    "api_payload",
                )
            )
            source = self._empty_dataframe(
                (
                    "_acubed_source_id",
                    "_acubed_chart_id",
                    "_acubed_collection_id",
                    "chart_base64",
                )
            )
            return DatabricksTableFrames(
                charts=charts,
                source=source,
                charts_count=0,
                source_count=0,
                _cached_frames=(),
            )

        # OPTIMIZATION: Increase parallelism for serverless compute
        # Use more slices for better distribution across serverless workers
        optimal_slices = max(len(assets) // 10, workers * 4, 1)

        assets_rdd = self.spark.sparkContext.parallelize(
            assets,
            numSlices=optimal_slices,
        )
        charts_rdd = assets_rdd.flatMap(_api_asset_to_bronze).cache()
        source_rdd = assets_rdd.flatMap(_api_asset_to_bronze_source).cache()

        charts = self._dataframe_from_rdd(
            charts_rdd,
            (
                "_acubed_chart_id",
                "_acubed_song_id",
                "_acubed_collection_id",
                "chart_title",
                "chart_artist",
                "difficulty_name",
                "difficulty",
                "keys",
                "api_payload",
            ),
        ).cache()
        source = self._dataframe_from_rdd(
            source_rdd,
            (
                "_acubed_source_id",
                "_acubed_chart_id",
                "_acubed_collection_id",
                "chart_base64",
            ),
        ).cache()

        return DatabricksTableFrames(
            charts=charts,
            source=source,
            charts_count=charts.count(),
            source_count=source.count(),
            _cached_frames=(charts, source, charts_rdd, source_rdd),
        )

    def table_exists(self, table_name: str) -> bool:
        qualified = self._get_qualified_name(table_name)
        return self.spark.catalog.tableExists(qualified)

    def read_table(self, table_name: str):
        qualified = self._get_qualified_name(table_name)
        return self.spark.table(qualified)

    def overwrite_table(self, table_name: str, dataframe) -> None:
        qualified = self._get_qualified_name(table_name)
        spark_df = self._ensure_spark_dataframe(dataframe)
        spark_df.write.format("delta").mode("overwrite").option(
            "overwriteSchema", "true"
        ).saveAsTable(qualified)

    def append_table(self, table_name: str, dataframe) -> None:
        qualified = self._get_qualified_name(table_name)
        spark_df = self._ensure_spark_dataframe(dataframe)

        if not self.table_exists(table_name):
            spark_df.write.format("delta").mode("append").saveAsTable(
                qualified
            )
            return

        target_columns = self.spark.table(qualified).columns
        reordered = spark_df.select(*target_columns)
        reordered.write.format("delta").mode("append").saveAsTable(qualified)

    def upsert_table(
        self, table_name: str, dataframe, key_columns: Sequence[str]
    ) -> None:

        qualified = self._get_qualified_name(table_name)
        spark_df = self._ensure_spark_dataframe(dataframe)

        # Check if table exists first
        if not self.table_exists(table_name):
            # Table doesn't exist - create it
            spark_df.write.format("delta").mode("overwrite").saveAsTable(
                qualified
            )
            return

        # Table exists - perform MERGE
        target_columns = set(self.spark.table(qualified).columns)
        update_expr = {
            col: f"source.{col}"
            for col in spark_df.columns
            if col in target_columns
        }

        source_view = "_merge_source"
        spark_df.createOrReplaceTempView(source_view)

        join_condition = " AND ".join(
            f"target.{col} = source.{col}" for col in key_columns
        )
        update_set = ", ".join(
            f"{col} = {expr}" for col, expr in update_expr.items()
        )

        sql = f"""
        MERGE INTO {qualified} AS target
        USING (SELECT * FROM {source_view}) AS source
        ON {join_condition}
        WHEN MATCHED THEN UPDATE SET {update_set}
        WHEN NOT MATCHED THEN INSERT *
        """

        self.spark.sql(sql)

    def drop_table(self, table_name: str) -> None:
        qualified = self._get_qualified_name(table_name)
        if self.table_exists(table_name):
            self.spark.sql(f"DROP TABLE IF EXISTS {qualified}")

    def optimize_tables(self, table_names: Iterable[str]) -> None:
        for table_name in table_names:
            qualified = self._get_qualified_name(table_name)
            if self.table_exists(table_name):
                self.spark.sql(f"OPTIMIZE {qualified}")
                self.spark.sql(f"VACUUM {qualified} RETAIN 168 HOURS")

    def iter_event_rows(
        self,
        table_name: str,
    ) -> Iterable[Mapping[str, Any]]:
        """Iterate over event rows from a table."""
        qualified = self._get_qualified_name(table_name)
        df = self.spark.table(qualified).orderBy("song_id", "note_id")

        for row in df.collect():
            yield {
                "song_id": row["song_id"],
                "note_id": row["note_id"],
                "time": row.get("time", row.get("timestamp_ms", 0)),
                "lane": row["lane"],
            }

    def sync_delta_table(
        self,
        table_name: str,
        dataframe,
        key_columns: Sequence[str],
    ) -> None:
        """Sync data to a Delta table using upsert (merge) logic."""
        # Use the existing upsert_table method
        self.upsert_table(table_name, dataframe, key_columns)
