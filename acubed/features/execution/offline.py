# features/execution/offline.py

import polars as pl
from features.compilers.polars import PolarsCompiler
from features.definitions.difficulty import (
    DIFFICULTY_FEATURES,
)


def build_training_features(
    df: pl.DataFrame,
) -> dict:

    compiler = PolarsCompiler()

    results = {}

    for feature in DIFFICULTY_FEATURES:
        expr = feature.expr.compile(compiler)

        value = df.select(expr.alias(feature.name)).item()

        results[feature.name] = value

    return results
