# models/game.py

from dataclasses import dataclass
from enum import StrEnum

from acubed.engine.ruleset import Ruleset


class Game(StrEnum):
    FFR = "ffr"
    ETTERNA = "etterna"
    QUAVER = "quaver"
    OSUMANIA = "osumania"


@dataclass(frozen=True, slots=True)
class GameMetadata:
    name: str

    lanes: int

    supports_holds: bool
    supports_long_notes: bool
    supports_mines: bool
    supports_scroll_velocity: bool

    timing_resolution_ms: int

    ruleset: Ruleset

    default_database: str
    default_catalog: str
