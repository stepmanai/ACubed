from acubed.domain.game.definition import GameDefinition
from acubed.plugins.osumania.config import OsuManiaConfig
from acubed.plugins.osumania.parser import OsuManiaChartParser
from acubed.plugins.osumania.source import OsuManiaRemoteSource

GAME_ID = "osumania"


def build_game() -> GameDefinition:
    config = OsuManiaConfig()

    return GameDefinition(
        id=GAME_ID,
        name="osu!mania",
        config=config,
        source=OsuManiaRemoteSource(config),
        parser=OsuManiaChartParser(),
        required_secrets={
            "client_id": "OSU_CLIENT_ID",
            "client_secret": "OSU_CLIENT_SECRET",
        },
    )


build_osumania_game = build_game
