# infrastructure/storage/base.py

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from typing import Any


class BaseStorage(ABC):
    @property
    @abstractmethod
    def catalog(self) -> str | None:
        pass

    @property
    @abstractmethod
    def schema(self) -> str:
        pass

    @abstractmethod
    def table_exists(
        self,
        table_name: str,
    ) -> bool:
        pass

    @abstractmethod
    def read_table(
        self,
        table_name: str,
    ):
        pass

    @abstractmethod
    def overwrite_table(
        self,
        table_name: str,
        dataframe,
    ):
        pass

    @abstractmethod
    def upsert_table(
        self,
        table_name: str,
        dataframe,
        key_columns: list[str],
    ):
        pass

    @abstractmethod
    def iter_event_rows(
        self,
        table_name: str,
    ) -> Iterable[Mapping[str, Any]]:
        pass
