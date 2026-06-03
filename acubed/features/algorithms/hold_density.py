import contextvars

from acubed.features.types import NoteFeature
from acubed.models.game import Game, GameMetadata
from acubed.models.registry import GAME_METADATA

GAME_CTX = contextvars.ContextVar(
    "game_ctx",
    default=Game.FFR,
)


def set_game(game: Game) -> None:
    GAME_CTX.set(game)


def get_game() -> Game:
    return GAME_CTX.get()


def get_game_metadata() -> GameMetadata:
    return GAME_METADATA[get_game()]


def hold_density(stepfile) -> NoteFeature:
    metadata = get_game_metadata()

    if not metadata.supports_holds:
        return {note: 0.0 for note in stepfile.notes}

    pass
    # density: NoteFeature = {}

    # for note in stepfile.notes:
    #     hold_weight = getattr(
    #       note, "hold_duration_ms", 0.0) if getattr(
    #       note, "is_hold", False) else 0.0
    #     density[note] = normalize_length(hold_weight)

    # return density
