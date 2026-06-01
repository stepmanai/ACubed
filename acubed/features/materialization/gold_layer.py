# features/materialization/gold_layer.py

import narwhals as nw

from acubed.core.runtime import RuntimeContext


def build_gold_note_features(
    context: RuntimeContext,
    silver_events_df: nw.LazyFrame,
) -> nw.LazyFrame:

    gold_note_features_df = silver_events_df

    print(context)
    print(gold_note_features_df)

    return gold_note_features_df
