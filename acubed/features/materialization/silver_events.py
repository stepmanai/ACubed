# features/materialization/silver_events.py

import polars as pl


def build_silver_events(
    bronze_df: pl.DataFrame,
) -> pl.DataFrame:

    rows = []

    for row in bronze_df.iter_rows(named=True):
        chart_id = row["song_id"]

        for idx, event in enumerate(row["chart"]):
            rows.append(
                {
                    "chart_id": chart_id,
                    "event_idx": idx,
                    "position": int(event[0]),
                    "lane": int(event[1]),
                    "note_type": int(event[2]),
                    "timestamp_ms": float(event[3]),
                }
            )

    return pl.DataFrame(rows)
