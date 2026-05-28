# storage/base.py

from abc import ABC, abstractmethod


class BaseStorage(ABC):
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

    # @abstractmethod
    # def delete_where_in(self, table_name: str, column: str, values: list):
    #     pass
