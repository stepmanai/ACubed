from __future__ import annotations

import os
from dataclasses import dataclass

from acubed.domain.game.protocols import GameConfig


def _env_int(name: str, default: int) -> int:
    try:
        return max(int(os.getenv(name, default)), 1)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class OsuManiaConfig(GameConfig):
    base_api_url: str = "https://osu.ppy.sh/api/v2"
    web_base_url: str = "https://osu.ppy.sh"
    token_url: str = "https://osu.ppy.sh/oauth/token"
    search_sort: str = "plays_desc"
    request_timeout: float = float(os.getenv("OSUMANIA_REQUEST_TIMEOUT", "30"))
    max_connections: int = _env_int("OSUMANIA_MAX_CONNECTIONS", 128)
    pack_asset_concurrency: int = _env_int(
        "OSUMANIA_PACK_ASSET_CONCURRENCY",
        4,
    )
    chart_asset_concurrency: int = _env_int(
        "OSUMANIA_CHART_ASSET_CONCURRENCY",
        32,
    )
    direct_batch_size: int = _env_int("OSUMANIA_DIRECT_BATCH_SIZE", 1000)
    direct_fallback: bool = os.getenv(
        "OSUMANIA_ALLOW_DIRECT_OSU_FALLBACK", "1"
    ).strip().lower() not in {"0", "false", "no"}
    asset_mode: str = (
        os.getenv("OSUMANIA_ASSET_MODE", "direct").strip().lower()
    )
