# storage/duckdb.py

import duckdb

from acubed.storage.base import BaseStorage


class DuckDBStorage(BaseStorage):
    def __init__(
        self,
        database_path: str,
    ):
        self.con = duckdb.connect(database=database_path)

    def _normalize_table_name(
        self,
        table_name: str,
    ) -> str:
        """
        Convert Databricks-style identifiers:

            catalog.schema.table

        into DuckDB-compatible identifiers:

            main.schema__table

        Example:
            acubed.ffr.bronze__playlist
            -> main.ffr__bronze__playlist
        """

        parts = table_name.split(".")

        if len(parts) == 3:
            _, schema, table = parts

            return f"main.{schema}__{table}"

        return table_name

    def table_exists(
        self,
        table_name,
    ):
        table_name = self._normalize_table_name(table_name)

        parts = table_name.split(".")

        if len(parts) == 2:
            schema, table = parts
        else:
            schema = "main"
            table = table_name

        result = self.con.execute(
            f"""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = '{schema}'
            AND table_name = '{table}'
            """
        ).fetchone()

        return result[0] > 0

    def read_table(
        self,
        table_name,
    ):
        table_name = self._normalize_table_name(table_name)

        return self.con.table(table_name)

    def overwrite_table(
        self,
        table_name,
        dataframe,
    ):
        table_name = self._normalize_table_name(table_name)

        self.con.sql(
            f"""
            CREATE OR REPLACE TABLE
            {table_name}
            AS
            SELECT *
            FROM dataframe
            """
        )

    def upsert_table(
        self,
        table_name,
        dataframe,
        key_columns,
    ):
        table_name = self._normalize_table_name(table_name)

        self.con.sql(
            """
            CREATE OR REPLACE TEMP TABLE
            temp_upsert
            AS
            SELECT *
            FROM dataframe
            """
        )

        delete_condition = " AND ".join(
            [f"{table_name}.{col} = temp_upsert.{col}" for col in key_columns]
        )

        self.con.sql(
            f"""
            DELETE FROM {table_name}
            USING temp_upsert
            WHERE {delete_condition}
            """
        )

        self.con.sql(
            f"""
            INSERT INTO {table_name}
            SELECT *
            FROM temp_upsert
            """
        )
