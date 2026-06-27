# infrastructure/storage/config.py

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StorageConfig:
    database_path: str | None = None
    catalog: str | None = None
    schema: str | None = None
