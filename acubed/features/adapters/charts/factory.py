# features/adapters/charts/factory.py

from acubed.models.gameplay import (
    Stepfile,
)

from .ffr import ffr_to_stepfile
from .sm import sm_to_stepfile


# TODO: RESOLVE THIS FACTORY.
def chart_to_stepfile(chart, game: str) -> Stepfile:
    match game:
        case "ffr":
            return ffr_to_stepfile(chart)

        case "etterna":
            return sm_to_stepfile(chart)

        case _:
            raise ValueError(f"Unsupported game: {game}")
