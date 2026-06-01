from acubed.features.adapters.charts.ffr import (
    ffr_to_stepfile,
)
from acubed.models.game import Game

_ADAPTERS = {
    Game.FFR: ffr_to_stepfile,
    # Game.ETTERNA: sm_to_stepfile,
    # Game.QUAVER: qua_to_stepfile,
    # Game.OSUMANIA: osu_to_stepfile,
}
