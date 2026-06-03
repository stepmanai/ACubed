# features/materialization/gold_layer.py
import subprocess
import sys
from collections import defaultdict

from acubed.features.adapters.stepfiles import (
    events_to_stepfile,
)
from acubed.features.algorithms.spatial_density import (
    spatial_density,
)
from acubed.features.algorithms.strain_requirement import (
    strain_requirement,
)
from acubed.features.algorithms.temporal_density import (
    temporal_density,
)

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

FEATURES = {
    "temporal_density": temporal_density,
    "spatial_density": spatial_density,
    "strain_requirement": strain_requirement,
}


def build_gold_note_features_local(
    rows,
) -> list[dict]:

    songs = defaultdict(list)

    for row in rows:
        songs[row["song_id"]].append(row)

    output = []

    for _, song_rows in songs.items():
        stepfile = events_to_stepfile(song_rows)

        feature_results = {
            name: feature(stepfile) for name, feature in FEATURES.items()
        }

        notes = next(iter(feature_results.values())).keys()

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
