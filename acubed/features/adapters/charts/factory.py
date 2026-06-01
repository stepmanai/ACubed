# features/adapters/charts/factory.py

from acubed.core.runtime import RuntimeContext
from acubed.models.game import Game
from acubed.models.gameplay import Stepfile

from .ffr import ffr_to_stepfile

_ADAPTERS = {
    Game.FFR: ffr_to_stepfile,
    # Game.ETTERNA: sm_to_stepfile,
    # Game.QUAVER: qua_to_stepfile,
    # Game.OSUMANIA: osu_to_stepfile,
}


def chart_to_stepfile(
    context: RuntimeContext,
    chart,
) -> Stepfile:
    try:
        adapter = _ADAPTERS[context.game]
    except KeyError as exc:
        raise ValueError(f"Unsupported game: {context.game}") from exc

    return adapter(chart)
