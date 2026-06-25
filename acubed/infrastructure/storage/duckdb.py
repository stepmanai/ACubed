# infrastructure/storage/duckdb.py

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import duckdb

from acubed.infrastructure.storage.base import BaseStorage


class DuckDBStorage(BaseStorage):
    def __init__(
        self,
        database_path: str,
        catalog: str | None = None,
        schema: str = "main",
    ):
        self.con = duckdb.connect(database=database_path)

        self._catalog = catalog
        self._schema = schema

        self.con.execute(
            f"""
            CREATE SCHEMA IF NOT EXISTS "{self.schema}"
            """
        )

    @property
    def catalog(self) -> str | None:
        return self._catalog

    @property
    def schema(self) -> str:
        return self._schema

    def _qualified_name(
        self,
        table_name: str,
    ) -> str:
        parts = table_name.split(".")

        if len(parts) == 3:
            _, schema, table = parts
            return f'"{schema}"."{table}"'

        if len(parts) == 2:
            schema, table = parts
            return f'"{schema}"."{table}"'

        return f'"{self.schema}"."{table_name}"'

    def table_exists(
        self,
        table_name: str,
    ) -> bool:
        qualified = self._qualified_name(table_name)

        schema, table = qualified.replace('"', "").split(".")

        result = self.con.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = ?
            AND table_name = ?
            """,
            [schema, table],
        ).fetchone()

        return result[0] > 0

    def read_table(
        self,
        table_name: str,
    ):
        return self.con.table(self._qualified_name(table_name))

    def overwrite_table(
        self,
        table_name: str,
        dataframe,
    ) -> None:
        qualified = self._qualified_name(table_name)

        self.con.register(
            "_acubed_dataframe",
            dataframe,
        )

        self.con.execute(
            f"""
            CREATE OR REPLACE TABLE {qualified}
            AS
            SELECT *
            FROM _acubed_dataframe
            """
        )

        self.con.unregister("_acubed_dataframe")

    def upsert_table(
        self,
        table_name: str,
        dataframe,
        key_columns: list[str],
    ) -> None:
        qualified = self._qualified_name(table_name)

        self.con.register(
            "_acubed_upsert",
            dataframe,
        )

        if not self.table_exists(table_name):
            self.overwrite_table(
                table_name,
                dataframe,
            )
            return

        delete_condition = " AND ".join(
            [f"target.{col} = source.{col}" for col in key_columns]
        )

        self.con.execute(
            """
            CREATE OR REPLACE TEMP TABLE temp_upsert
            AS
            SELECT *
            FROM _acubed_upsert
            """
        )

        self.con.execute(
            f"""
            DELETE FROM {qualified} AS target
            USING temp_upsert AS source
            WHERE {delete_condition}
            """
        )

        self.con.execute(
            f"""
            INSERT INTO {qualified}
            SELECT *
            FROM temp_upsert
            """
        )

        self.con.unregister("_acubed_upsert")

    def iter_event_rows(
        self,
        table_name: str,
    ) -> Iterable[dict[str, Any]]:
        relation = self.read_table(table_name)

        columns = relation.columns

        for values in relation.order("song_id ASC, note_id ASC").fetchall():
            row = dict(zip(columns, values, strict=False))

            yield {
                "song_id": row["song_id"],
                "note_id": row["note_id"],
                "time": row["time"],
                "lane": row["lane"],
            }
