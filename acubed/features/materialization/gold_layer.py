# features/materialization/gold_layer.py

import narwhals as nw

from acubed.features.algorithms.vertical_density import (
    vertical_density,
)


def build_gold_note_features(
    silver_events_df: nw.LazyFrame,
) -> nw.LazyFrame:

    return vertical_density(silver_events_df)
