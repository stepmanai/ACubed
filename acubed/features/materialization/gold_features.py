# features/materialization/gold_features.py

import polars as pl

from acubed.features.adapters.charts import (
    chart_to_stepfile,
)
from acubed.features.executors.runtime import (
    build_features,
)


def build_gold_features(
    bronze_df: pl.DataFrame,
) -> pl.DataFrame:

    rows = []

    for row in bronze_df.iter_rows(named=True):
        info = row["info"]

        difficulty = (
            float(info.get("difficulty", 0)) if isinstance(info, dict) else 0.0
        )

        stepfile = chart_to_stepfile(
            row["chart"],
            difficulty=difficulty,
        )

        features = build_features(
            chart_id=row["song_id"],
            stepfile=stepfile,
        )

        rows.append(
            {
                **features.__dict__,
                "difficulty": difficulty,
            }
        )

    return pl.DataFrame(rows)
