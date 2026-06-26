from dataclasses import dataclass


@dataclass(frozen=True)
class TableConfig:
    # songlist: str
    charts: str
    notes: str
    # playlist: str


def build_table_config(game_id: str) -> TableConfig:
    return TableConfig(
        charts="bronze__charts",
        notes="bronze__notes",
    )
