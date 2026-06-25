from dataclasses import dataclass


@dataclass(frozen=True)
class TableConfig:
    # songlist: str
    charts: str
    notes: str
    # playlist: str


def build_table_config(game_id: str) -> TableConfig:
    return TableConfig(
        # songlist=f"{game_id}_songlist",
        charts=f"{game_id}_charts",
        notes=f"{game_id}_notes",
        # playlist=f"{game_id}_playlist",
    )
