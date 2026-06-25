# runtime/settings.py

from __future__ import annotations

import os
from dataclasses import dataclass

from acubed.infrastructure.storage.config import StorageConfig


@dataclass(frozen=True)
class RuntimeConfig:
    game: str = os.getenv("GAME", "quaver")
    thread_pool_size: int = int(os.getenv("THREAD_POOL_SIZE", 4))
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", 10))
    max_retries: int = int(os.getenv("MAX_RETRIES", 5))


@dataclass(frozen=True)
class RuntimeSettings:
    runtime: RuntimeConfig
    storage: StorageConfig
