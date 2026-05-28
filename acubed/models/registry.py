# models/registry.py

from acubed.config.runtime import config
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
        default_database=config.local_db_path,
    ),
}
