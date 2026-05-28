# config/settings.py

from dataclasses import dataclass

from acubed.models.game import Game
from acubed.models.registry import GAME_METADATA

DEFAULT_GAME = Game.FFR


@dataclass(frozen=True)
class DuckDBSettings:
    database_path: str


@dataclass(frozen=True)
class DatabricksSettings:
    catalog: str
    schema: str


def build_duckdb_settings(
    game: Game = DEFAULT_GAME,
) -> DuckDBSettings:
    metadata = GAME_METADATA[game]

    return DuckDBSettings(
        database_path=metadata.default_database,
    )


def build_databricks_settings(
    game: Game = DEFAULT_GAME,
) -> DatabricksSettings:

    return DatabricksSettings(
        catalog="acubed",
        schema=game.value,
    )
