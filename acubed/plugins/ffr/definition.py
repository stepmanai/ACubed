# plugins/ffr/definition.py

from acubed.domain.game.definition import GameDefinition
from acubed.plugins.ffr.config import FFRConfig
from acubed.plugins.ffr.parser import FFRChartParser
from acubed.plugins.ffr.source import FFRRemoteSource

GAME_ID = "ffr"


def build_game() -> GameDefinition:
    config = FFRConfig()

    return GameDefinition(
        id=GAME_ID,
        name="Flash Flash Revolution",
        config=config,
        source=FFRRemoteSource(config),
        parser=FFRChartParser(),
        required_secrets={"key": "FFR_API_KEY"},
    )


build_ffr_game = build_game
