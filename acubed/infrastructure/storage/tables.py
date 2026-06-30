from dataclasses import dataclass


@dataclass(frozen=True)
class TableConfig:
    # songlist: str
    collections: str
    charts: str
    source: str
    # playlist: str


def build_table_config(game_id: str) -> TableConfig:
    return TableConfig(
        collections="bronze__collections",
        charts="bronze__charts",
        source="bronze__source",
    )
