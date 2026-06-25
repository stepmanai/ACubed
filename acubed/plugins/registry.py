"""Game plugin discovery and lookup."""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from pkgutil import iter_modules

import acubed.plugins
from acubed.domain.game.definition import GameDefinition


class PluginRegistry:
    def __init__(self) -> None:
        self._builders: dict[
            str,
            Callable[[], GameDefinition],
        ] = {}

    def register(
        self,
        game_id: str,
        builder: Callable[[], GameDefinition],
    ) -> None:
        if game_id in self._builders:
            raise ValueError(f"Duplicate game plugin registered: {game_id}")

        self._builders[game_id] = builder

    def get(self, game_id: str) -> GameDefinition:
        try:
            return self._builders[game_id]()
        except KeyError as err:
            available = ", ".join(self.available()) or "none"
            raise ValueError(
                f"Unknown game: {game_id}. Available games: {available}"
            ) from err

    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self._builders))


def discover_plugins() -> PluginRegistry:
    discovered = PluginRegistry()

    for module_info in iter_modules(acubed.plugins.__path__):
        if not module_info.ispkg:
            continue

        definition_module = import_module(
            f"{acubed.plugins.__name__}.{module_info.name}.definition"
        )

        game_id = getattr(definition_module, "GAME_ID", module_info.name)
        builder = getattr(definition_module, "build_game", None)

        if builder is None:
            legacy_name = f"build_{game_id}_game"
            builder = getattr(definition_module, legacy_name, None)

        if builder is None:
            raise ValueError(
                f"Game plugin '{game_id}' must expose build_game()"
            )

        discovered.register(game_id, builder)

    return discovered


registry = discover_plugins()
