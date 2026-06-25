# runtime/context.py

from __future__ import annotations

from dataclasses import dataclass

from acubed.domain.game.definition import (
    GameDefinition,
)
from acubed.infrastructure.environment.types import (
    Environment,
)
from acubed.runtime.settings import RuntimeConfig


@dataclass
class RuntimeContext:
    environment: Environment
    game: GameDefinition
    settings: RuntimeConfig
