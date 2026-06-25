# plugins/ffr/config.py

from dataclasses import dataclass

from acubed.domain.game.protocols import GameConfig


@dataclass(frozen=True)
class QuaverConfig(GameConfig):
    base_api_url: str = "https://api.quavergame.com/"
