# plugins/ffr/config.py

from dataclasses import dataclass

from acubed.domain.game.protocols import GameConfig


@dataclass(frozen=True)
class FFRConfig(GameConfig):
    base_api_url: str = "https://www.flashflashrevolution.com/api/api.php"

    playlist_url: str = (
        "https://www.flashflashrevolution.com/game/r3/r3-playlist.php"
    )
