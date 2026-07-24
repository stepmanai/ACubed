# plugins/ffr/definition.py

from acubed.domain.game.plugin import GamePlugin
from acubed.plugins.ffr.config import FFRConfig
from acubed.plugins.ffr.parser import FFRChartParser
from acubed.plugins.ffr.source import FFRRemoteSource

GAME_ID = "ffr"

PLUGIN = GamePlugin(
    id=GAME_ID,
    name="Flash Flash Revolution",
    config_factory=FFRConfig,
    source_factory=FFRRemoteSource,
    parser_factory=FFRChartParser,
    required_secrets={"key": "FFR_API_KEY"},
)
build_game = PLUGIN.build
build_ffr_game = build_game
