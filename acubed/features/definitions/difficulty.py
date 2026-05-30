# features/definitions/difficulty.py

from dataclasses import dataclass

from features.expressions.aggregations import (
    Avg,
    StdDev,
)
from features.expressions.base import Column


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    expr: object


AVG_OFFSET = FeatureDefinition(
    name="avg_hit_offset",
    expr=Avg(Column("hit_offset_ms")),
)

TIMING_VARIANCE = FeatureDefinition(
    name="timing_variance",
    expr=StdDev(Column("hit_offset_ms")),
)

DIFFICULTY_FEATURES = [
    AVG_OFFSET,
    TIMING_VARIANCE,
]
