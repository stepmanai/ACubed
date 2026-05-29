# models/registry.py

from acubed.config.paths import DUCKDB_PATH
from acubed.engine.objectives.ffr import (
    FFR_OBJECTIVE,
)
from acubed.models.game import (
    Game,
    GameMetadata,
)

GAME_METADATA = {
    Game.FFR: GameMetadata(
        name="Flash Flash Revolution",
        lanes=4,
        supports_holds=False,
        supports_long_notes=False,
        supports_mines=False,
        timing_resolution_ms=1,
        objective=FFR_OBJECTIVE,
        default_database=DUCKDB_PATH,
    ),
}
