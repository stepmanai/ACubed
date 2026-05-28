# models/game.py

from dataclasses import dataclass
from enum import StrEnum

from acubed.engine.objective import Objective


class Game(StrEnum):
    FFR = "ffr"
    # ETTERNA = "etterna"
    # QUAVER = "quaver"
    # OSUMANIA = "osumania"


@dataclass(frozen=True, slots=True)
class GameMetadata:
    name: str

    lanes: int

    supports_holds: bool
    supports_long_notes: bool
    supports_mines: bool

    timing_resolution_ms: int

    objective: Objective

    default_database: str
