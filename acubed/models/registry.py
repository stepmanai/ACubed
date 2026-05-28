# models/registry.py

from acubed.models.game import (
    Game,
    GameMetadata,
)

from acubed.engine.rulesets.ffr import (
    FFR_RULESET,
)


GAME_METADATA = {
    Game.FFR: GameMetadata(
        name="Flash Flash Revolution",

        lanes=4,

        supports_holds=False,
        supports_long_notes=False,
        supports_mines=False,
        supports_scroll_velocity=False,

        timing_resolution_ms=1,

        ruleset=FFR_RULESET,

        default_database="acubed.duckdb",
        default_catalog="acubed",
    ),
}