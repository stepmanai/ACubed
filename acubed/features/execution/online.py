# features/execution/online.py

from features.compilers.runtime import RuntimeCompiler
from features.definitions.difficulty import (
    DIFFICULTY_FEATURES,
)


def build_online_features(events):

    compiler = RuntimeCompiler()

    features = {}

    for feature in DIFFICULTY_FEATURES:
        fn = feature.expr.compile(compiler)

        features[feature.name] = fn(events)

    return features
