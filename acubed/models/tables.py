# models/tables.py

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TableDefinition:
    name: str
    primary_keys: tuple[str, ...]
