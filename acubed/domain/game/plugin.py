"""Declarative game-plugin construction."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from acubed.domain.game.definition import GameDefinition
from acubed.domain.game.protocols import ChartParser, ChartSource, GameConfig

ConfigT = TypeVar("ConfigT", bound=GameConfig)


@dataclass(frozen=True)
class GamePlugin(Generic[ConfigT]):
    """Factories and metadata required to add a game to ACubed."""

    id: str
    name: str
    config_factory: Callable[[], ConfigT]
    source_factory: Callable[[ConfigT], ChartSource]
    parser_factory: Callable[[], ChartParser]
    required_secrets: Mapping[str, str] = field(default_factory=dict)

    def build(self) -> GameDefinition:
        config = self.config_factory()
        return GameDefinition(
            id=self.id,
            name=self.name,
            config=config,
            source=self.source_factory(config),
            parser=self.parser_factory(),
            required_secrets=dict(self.required_secrets),
        )
