# validation/notes.py

from acubed.models.game import Game
from acubed.models.registry import GAME_METADATA


def validate_lanes(df, game: Game):
    metadata = GAME_METADATA[game]

    max_lane = metadata.lanes - 1

    return df.filter(df["lane"] <= max_lane)
