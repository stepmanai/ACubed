"""Game plugin discovery and lookup."""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from pkgutil import iter_modules
from types import ModuleType

import acubed.plugins
from acubed.domain.game.definition import GameDefinition
from acubed.domain.game.plugin import GamePlugin

GameBuilder = Callable[[], GameDefinition]


class PluginRegistry:
    def __init__(self) -> None:
        self._builders: dict[str, GameBuilder] = {}

    def register(
        self,
        game_id: str,
        builder: GameBuilder,
    ) -> None:
        if game_id in self._builders:
            raise ValueError(f"Duplicate game plugin registered: {game_id}")

        self._builders[game_id] = builder

    def get(self, game_id: str) -> GameDefinition:
        try:
            builder = self._builders[game_id]
        except KeyError as err:
            available = ", ".join(self.available()) or "none"
            raise ValueError(
                f"Unknown game: {game_id}. Available games: {available}"
            ) from err
        return builder()

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

        game_id, builder = _plugin_entrypoint(
            definition_module, module_info.name
        )
        discovered.register(game_id, builder)

    return discovered


def _plugin_entrypoint(
    module: ModuleType,
    package_name: str,
) -> tuple[str, GameBuilder]:
    plugin = getattr(module, "PLUGIN", None)
    if isinstance(plugin, GamePlugin):
        return plugin.id, plugin.build

    game_id = getattr(module, "GAME_ID", package_name)
    builder = getattr(module, "build_game", None) or getattr(
        module, f"build_{game_id}_game", None
    )
    if not callable(builder):
        raise ValueError(
            f"Game plugin '{game_id}' must expose PLUGIN or build_game()"
        )
    return game_id, builder


registry = discover_plugins()
