from __future__ import annotations

import os
from dataclasses import dataclass

from acubed.domain.game.protocols import GameConfig
from acubed.infrastructure.environment.variables import (
    env_bool,
    env_float,
    env_int,
)


@dataclass(frozen=True)
class OsuManiaConfig(GameConfig):
    base_api_url: str = "https://osu.ppy.sh/api/v2"
    web_base_url: str = "https://osu.ppy.sh"
    token_url: str = "https://osu.ppy.sh/oauth/token"
    search_sort: str = "plays_desc"
    request_timeout: float = env_float("OSUMANIA_REQUEST_TIMEOUT", 30.0)
    max_connections: int = env_int("OSUMANIA_MAX_CONNECTIONS", 128, minimum=1)
    pack_asset_concurrency: int = env_int(
        "OSUMANIA_PACK_ASSET_CONCURRENCY",
        4,
        minimum=1,
    )
    chart_asset_concurrency: int = env_int(
        "OSUMANIA_CHART_ASSET_CONCURRENCY",
        32,
        minimum=1,
    )
    direct_batch_size: int = env_int(
        "OSUMANIA_DIRECT_BATCH_SIZE",
        1000,
        minimum=1,
    )
    direct_fallback: bool = env_bool(
        "OSUMANIA_ALLOW_DIRECT_OSU_FALLBACK", True
    )
    asset_mode: str = (
        os.getenv("OSUMANIA_ASSET_MODE", "direct").strip().lower()
    )
