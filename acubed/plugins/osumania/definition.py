from acubed.domain.game.plugin import GamePlugin
from acubed.plugins.osumania.config import OsuManiaConfig
from acubed.plugins.osumania.parser import OsuManiaChartParser
from acubed.plugins.osumania.source import OsuManiaRemoteSource

GAME_ID = "osumania"

PLUGIN = GamePlugin(
    id=GAME_ID,
    name="osu!mania",
    config_factory=OsuManiaConfig,
    source_factory=OsuManiaRemoteSource,
    parser_factory=OsuManiaChartParser,
    required_secrets={
        "client_id": "OSU_CLIENT_ID",
        "client_secret": "OSU_CLIENT_SECRET",
    },
)
build_game = PLUGIN.build
build_osumania_game = build_game
