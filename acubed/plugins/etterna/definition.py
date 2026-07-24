# plugins/etterna/definition.py

from acubed.domain.game.plugin import GamePlugin
from acubed.plugins.etterna.config import EtternaConfig
from acubed.plugins.etterna.parser import EtternaChartParser
from acubed.plugins.etterna.source import EtternaRemoteSource

GAME_ID = "etterna"

PLUGIN = GamePlugin(
    id=GAME_ID,
    name="Etterna",
    config_factory=EtternaConfig,
    source_factory=EtternaRemoteSource,
    parser_factory=EtternaChartParser,
)
build_game = PLUGIN.build
build_etterna_game = build_game
