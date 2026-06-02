# features/materialization/silver_layer.py
import subprocess
import sys

try:
    import narwhals as nw
except ImportError:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "narwhals"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    import narwhals as nw


def build_silver_events(
    bronze_df: nw.LazyFrame,
) -> nw.LazyFrame:

    silver_events_df = (
        bronze_df.explode("chart")
        .with_columns(
            song_name=nw.col("info").struct.field("name"),
            framer=nw.col("chart").list.get(0),
            lane=nw.col("chart").list.get(1),
            color=nw.col("chart").list.get(2),
            time=nw.col("chart").list.get(3),
        )
        .with_columns(
            note_id=nw.col("song_id")
            .cum_count()
            .over("song_id", order_by="time")
        )
        .drop("chart", "info")
    )

    return silver_events_df
