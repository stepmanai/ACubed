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
from acubed.infrastructure.storage.tables import TableConfig
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

    def _ensure_spark_dataframe(self, dataframe):
        if hasattr(dataframe, "write"):
            return dataframe

        return self.spark.createDataFrame(dataframe)

    def _empty_dataframe(self, columns: Sequence[str]):
        from pyspark.sql.types import (
            DoubleType,
            LongType,
            StringType,
            StructField,
            StructType,
        )

        numeric_types = {
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
        }

        return self.spark.createDataFrame(
            [],
            StructType(
                [
                    StructField(column, numeric_types[column], True)
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

        # OPTIMIZATION: Process both charts and source in single pass
        # to avoid re-scanning the RDD
        charts_rdd = assets_rdd.flatMap(_api_asset_to_bronze)
        source_rdd = assets_rdd.flatMap(_api_asset_to_bronze_source)

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

        # OPTIMIZATION: Trigger count() to cache dataframes before returning
        # This ensures data is materialized in cache before MERGE operations
        charts_count = charts.count()
        source_count = source.count()

        return DatabricksTableFrames(
            charts=charts,
            source=source,
            charts_count=charts_count,
            source_count=source_count,
            _cached_frames=(charts, source),
        )

    def table_exists(self, table_name: str) -> bool:
        qualified = self._get_qualified_name(table_name)
        return self.spark.catalog.tableExists(qualified)

    def read_table(self, table_name: str):
        qualified = self._get_qualified_name(table_name)
        return self.spark.table(qualified)

    def overwrite_table(
        self,
        table_name: str,
        dataframe,
    ) -> None:
        qualified = self._get_qualified_name(table_name)
        spark_df = self._ensure_spark_dataframe(dataframe)
        (
            spark_df.write.format("delta")
            .mode("overwrite")
            .option("overwriteSchema", "true")
            .saveAsTable(qualified)
        )

    def upsert_table(
        self,
        table_name: str,
        dataframe,
        key_columns: Sequence[str],
    ) -> None:
        qualified = self._get_qualified_name(table_name)
        spark_df = self._ensure_spark_dataframe(dataframe)
        temp_view = f"_acubed_upsert_{abs(hash(qualified))}"

        # OPTIMIZATION: Coalesce small batches to reduce shuffle overhead
        # For batches < 1000 rows, use single partition to avoid shuffle
        row_count = spark_df.count()
        if row_count < 1000:
            spark_df = spark_df.coalesce(1)
        elif row_count < 10000:
            # For medium batches, use limited partitions
            spark_df = spark_df.coalesce(min(row_count // 500, 20))

        spark_df.createOrReplaceTempView(temp_view)

        if not self.table_exists(table_name):
            self.overwrite_table(table_name, spark_df)
            return

        target_columns = self.spark.table(qualified).columns
        assignments = ", ".join(
            f"target.`{col}` = source.`{col}`" for col in target_columns
        )
        insert_columns = ", ".join(f"`{col}`" for col in target_columns)
        insert_values = ", ".join(f"source.`{col}`" for col in target_columns)
        merge_condition = " AND ".join(
            f"target.`{col}` = source.`{col}`" for col in key_columns
        )

        self.spark.sql(
            f"""
            MERGE INTO {qualified} AS target
            USING `{temp_view}` AS source
            ON {merge_condition}
            WHEN MATCHED THEN UPDATE SET {assignments}
            WHEN NOT MATCHED THEN INSERT ({insert_columns})
            VALUES ({insert_values})
            """
        )

    def sync_delta_table(
        self,
        table_name: str,
        dataframe,
        key_columns: Sequence[str],
        partition_columns: Sequence[str] | None = None,
    ) -> str:
        qualified = self._get_qualified_name(table_name)
        spark_df = self._ensure_spark_dataframe(dataframe)

        if not self.table_exists(table_name):
            writer = spark_df.write.format("delta").mode("overwrite")
            if partition_columns:
                writer = writer.partitionBy(*partition_columns)
            writer.saveAsTable(qualified)
            return "created"

        target_columns = set(self.spark.table(qualified).columns)
        source_columns = set(spark_df.columns)
        if (
            not set(key_columns).issubset(target_columns)
            or target_columns != source_columns
        ):
            writer = (
                spark_df.write.format("delta")
                .mode("overwrite")
                .option("overwriteSchema", "true")
            )
            if partition_columns:
                writer = writer.partitionBy(*partition_columns)
            writer.saveAsTable(qualified)
            return "replaced"

        self.upsert_table(table_name, spark_df, key_columns)
        return "merged"

    def sync_ingestion_tables(
        self,
        table_config: TableConfig,
        frames: DatabricksTableFrames,
    ) -> dict[str, str]:
        chart_action = self.sync_delta_table(
            table_config.charts,
            frames.charts,
            key_columns=("_acubed_chart_id",),
        )
        actions = {
            table_config.charts: chart_action,
        }
        if frames.source is not None:
            actions[table_config.source] = self.sync_delta_table(
                table_config.source,
                frames.source,
                key_columns=("_acubed_source_id",),
            )

        return actions

    def optimize_tables(self, table_names: Sequence[str]) -> None:
        for table_name in table_names:
            qualified = self._get_qualified_name(table_name)
            self.spark.sql(f"OPTIMIZE {qualified}")
            self.spark.sql(
                f"ANALYZE TABLE {qualified} COMPUTE STATISTICS FOR ALL COLUMNS"
            )

    def iter_event_rows(
        self,
        table_name: str,
    ) -> Iterable[Mapping[str, Any]]:
        df = self.read_table(table_name)
        rows = (
            df.select("song_id", "note_id", "time", "lane")
            .orderBy("song_id", "note_id")
            .collect()
        )

        for row in rows:
            yield {
                "song_id": row["song_id"],
                "note_id": row["note_id"],
                "time": row["time"],
                "lane": row["lane"],
            }
