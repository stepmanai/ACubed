#

from __future__ import annotations

from dataclasses import dataclass

from acubed.infrastructure.storage.config import StorageConfig


@dataclass(frozen=True)
class RuntimeConfig:
    game: str
    thread_pool_size: int
    request_timeout: int
    max_retries: int


@dataclass(frozen=True)
class RuntimeSettings:
    runtime: RuntimeConfig
    storage: StorageConfig
