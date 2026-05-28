# core/runtime.py

from dataclasses import dataclass

from acubed.models.environment import (
    Environment,
)

from acubed.models.game import Game


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    environment: Environment
    game: Game