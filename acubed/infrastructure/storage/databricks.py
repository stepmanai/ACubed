"""Databricks storage adapter.

This module intentionally relies on the Spark session provided by Databricks.
Do not add pyspark, databricks-connect, or delta-spark as project dependencies;
serverless Databricks environments provide the Spark client runtime.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from acubed.domain.game.definition import GameDefinition
from acubed.infrastructure.storage.base import BaseStorage


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
