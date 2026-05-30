# config/runtime.py

import os
from dataclasses import (
    dataclass,
)

from dotenv import load_dotenv

from acubed.models.game import (
    Game,
)

load_dotenv()


@dataclass(
    frozen=True,
    slots=True,
)
class RuntimeConfig:
    base_api_url: str = "https://www.flashflashrevolution.com/api/api.php"

    playlist_url: str = (
        "https://www.flashflashrevolution.com/game/r3/r3-playlist.php"
    )

    thread_pool_size: int = int(
        os.getenv(
            "THREAD_POOL_SIZE",
            4,
        )
    )

    request_timeout: int = int(
        os.getenv(
            "REQUEST_TIMEOUT",
            10,
        )
    )

    max_retries: int = int(
        os.getenv(
            "MAX_RETRIES",
            5,
        )
    )

    game: Game = Game.FFR


config = RuntimeConfig()
