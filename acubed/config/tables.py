# config/tables.py

from dataclasses import dataclass

from acubed.models.game import Game


@dataclass(frozen=True, slots=True)
class TableConfig:
    songlist: str
    charts: str
    playlist: str
    silver_events: str
    silver_songs: str
    gold_features: str


def build_table_config(
    game: Game,
    catalog: str,
):
    schema = game.value

    return TableConfig(
        songlist=(f"{catalog}.{schema}.bronze__songlist"),
        charts=(f"{catalog}.{schema}.bronze__charts"),
        playlist=(f"{catalog}.{schema}.bronze__playlist"),
        silver_events=(f"{catalog}.{schema}.silver__events"),
        silver_songs=(f"{catalog}.{schema}.silver__songs"),
        gold_features=(f"{catalog}.{schema}.gold__features"),
    )
