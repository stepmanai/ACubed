# plugins/quaver/definition.py

from acubed.domain.game.plugin import GamePlugin
from acubed.plugins.quaver.config import QuaverConfig
from acubed.plugins.quaver.parser import QuaverChartParser
from acubed.plugins.quaver.source import QuaverRemoteSource

GAME_ID = "quaver"

PLUGIN = GamePlugin(
    id=GAME_ID,
    name="Quaver",
    config_factory=QuaverConfig,
    source_factory=QuaverRemoteSource,
    parser_factory=QuaverChartParser,
)
build_game = PLUGIN.build
build_quaver_game = build_game
