"""Domain model for supported games."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from acubed.domain.game.protocols import ChartParser, ChartSource, GameConfig


@dataclass(frozen=True)
class GameDefinition:
    id: str
    name: str
    config: GameConfig
    source: ChartSource
    parser: ChartParser
    required_secrets: Mapping[str, str] = field(default_factory=dict)
