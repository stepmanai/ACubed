# storage/databricks.py

from delta.tables import DeltaTable

from acubed.models.game import Game
from acubed.storage.base import BaseStorage


class DatabricksStorage(BaseStorage):
    def __init__(
        self,
        spark,
        game: Game,
    ):
        self.spark = spark

        self.catalog = "acubed"

        self.schema = game.value

    @property
    def namespace(self):
        return f"{self.catalog}.{self.schema}"

    def _get_qualified_name(self, table_name):
        parts = table_name.split(".")
        if len(parts) == 3:
            return table_name
        else:
            return f"{self.namespace}.{table_name}"

    def _ensure_spark_dataframe(self, dataframe):
        if hasattr(dataframe, "write"):
            return dataframe
        else:
            return self.spark.createDataFrame(dataframe)

    def table_exists(self, table_name: str) -> bool:
        qualified = self._get_qualified_name(table_name)
        return self.spark.catalog.tableExists(qualified)

    def read_table(self, table_name):
        qualified = self._get_qualified_name(table_name)
        return self.spark.table(qualified)

    def overwrite_table(
        self,
        table_name,
        dataframe,
    ):
        qualified = self._get_qualified_name(table_name)
        spark_df = self._ensure_spark_dataframe(dataframe)
        (
            spark_df.write.format("delta")
            .mode("overwrite")
            .option(
                "overwriteSchema",
                "true",
            )
            .saveAsTable(qualified)
        )

    def upsert_table(
        self,
        table_name,
        dataframe,
        key_columns,
    ):
        qualified = self._get_qualified_name(table_name)
        spark_df = self._ensure_spark_dataframe(dataframe)

        delta_table = DeltaTable.forName(
            self.spark,
            qualified,
        )

        condition = " AND ".join(
            [f"target.{c} = source.{c}" for c in key_columns]
        )

        (
            delta_table.alias("target")
            .merge(
                spark_df.alias("source"),
                condition,
            )
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
