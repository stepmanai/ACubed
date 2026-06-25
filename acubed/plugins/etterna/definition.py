# plugins/etterna/definition.py

from acubed.domain.game.definition import GameDefinition
from acubed.plugins.etterna.config import EtternaConfig
from acubed.plugins.etterna.parser import EtternaChartParser
from acubed.plugins.etterna.source import EtternaRemoteSource

GAME_ID = "etterna"


def build_game() -> GameDefinition:
    config = EtternaConfig()

    return GameDefinition(
        id=GAME_ID,
        name="Etterna",
        config=config,
        source=EtternaRemoteSource(config),
        parser=EtternaChartParser(),
    )


build_etterna_game = build_game
