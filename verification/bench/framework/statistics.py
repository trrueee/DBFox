"""Small dependency-free statistical summaries shared by benchmark suites."""

from __future__ import annotations

import math
import statistics
from typing import Iterable


def wilson_interval(
    successes: int,
    total: int,
    z: float = 1.959963984540054,
) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 0.0)
    proportion = successes / total
    denominator = 1 + (z * z / total)
    centre = proportion + (z * z / (2 * total))
    margin = z * math.sqrt(
        (proportion * (1 - proportion) / total) + (z * z / (4 * total * total))
    )
    return ((centre - margin) / denominator, (centre + margin) / denominator)


def percentile(values: Iterable[float], percentile_value: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile_value
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def distribution(values: Iterable[float]) -> dict[str, float]:
    items = [float(value) for value in values]
    if not items:
        return {"median": 0.0, "p90": 0.0, "maximum": 0.0}
    return {
        "median": statistics.median(items),
        "p90": percentile(items, 0.90),
        "maximum": max(items),
    }
