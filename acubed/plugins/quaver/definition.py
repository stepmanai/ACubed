# plugins/quaver/definition.py

from acubed.domain.game.definition import GameDefinition
from acubed.plugins.quaver.config import QuaverConfig
from acubed.plugins.quaver.parser import QuaverChartParser
from acubed.plugins.quaver.source import QuaverRemoteSource

GAME_ID = "quaver"


def build_game() -> GameDefinition:
    config = QuaverConfig()

    return GameDefinition(
        id=GAME_ID,
        name="Quaver",
        config=config,
        source=QuaverRemoteSource(config),
        parser=QuaverChartParser(),
    )


build_quaver_game = build_game
