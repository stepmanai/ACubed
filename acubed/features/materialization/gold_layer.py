# features/materialization/gold_layer.py
import subprocess
import sys

from acubed.features.adapters.stepfiles import (
    events_to_stepfile,
)
from acubed.features.algorithms.vertical_density import (
    vertical_density,
)

try:
    import narwhals as nw
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "narwhals"])
    import narwhals as nw

FEATURES = {
    "vertical_density": vertical_density,
    # "chord_density": chord_density,
    # "stream_density": stream_density,
    # "jack_density": jack_density,
}


def build_gold_note_features_local(
    rows,
) -> list[dict]:

    stepfile = events_to_stepfile(rows)

    feature_results = {
        name: feature(stepfile) for name, feature in FEATURES.items()
    }

    notes = next(iter(feature_results.values())).keys()

    output = []

    for note in notes:
        row = {
            "song_id": note.song_id,
            "note_id": note.note_id,
            "time": note.timestamp_ms,
            "lane": note.lane.value,
        }

        for feature_name, values in feature_results.items():
            row[feature_name] = values[note]

        output.append(row)

    return output


def _compute_song_features(song_events):

    rows = [
        {
            "song_id": row["song_id"],
            "note_id": row["note_id"],
            "time": row["time"],
            "lane": row["lane"],
        }
        for row in song_events
    ]

    return build_gold_note_features_local(rows)


def build_gold_note_features_spark(spark_df):

    import pandas as pd
    from pyspark.sql.types import (
        FloatType,
        IntegerType,
        StructField,
        StructType,
    )

    output_schema = StructType(
        [
            StructField("song_id", IntegerType(), False),
            StructField("note_id", IntegerType(), False),
            StructField("time", FloatType(), False),
            StructField("lane", IntegerType(), False),
        ]
        + [StructField(name, FloatType(), True) for name in FEATURES.keys()]
    )

    def process_song_partition(iterator):

        for pdf in iterator:
            if pdf.empty:
                yield pd.DataFrame(
                    columns=["song_id", "note_id", "time", "lane"]
                    + list(FEATURES.keys())
                )
                continue

            results = []
            for _, group in pdf.groupby("song_id"):
                rows = group.to_dict("records")

                song_features = build_gold_note_features_local(rows)
                results.extend(song_features)

            yield pd.DataFrame(results)

    result_df = spark_df.mapInPandas(
        process_song_partition, schema=output_schema
    )

    return result_df


def build_gold_note_features(
    rows_or_df,
    use_spark=None,
):
    if use_spark is None:
        use_spark = (
            hasattr(rows_or_df, "write")
            and "pyspark" in type(rows_or_df).__module__
        )

    if use_spark:
        return build_gold_note_features_spark(rows_or_df)
    else:
        return build_gold_note_features_local(rows_or_df)


def build_gold_targets(
    bronze_df: nw.LazyFrame,
) -> nw.LazyFrame:

    gold_targets_df = (
        bronze_df.with_columns(
            song_id=nw.col("level"),
        )
        .select(
            "song_id",
            "name",
            "difficulty",
            "previewhash",
        )
        .sort("song_id")
    )

    return gold_targets_df
