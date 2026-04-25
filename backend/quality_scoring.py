from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Iterable


def clamp(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    return max(min_value, min(max_value, value))


def size_bucket(estate_type: str, usable_area: float | None) -> str:
    if usable_area is None:
        return "unknown"
    if estate_type == "land":
        if usable_area < 400:
            return "tiny"
        if usable_area < 800:
            return "small"
        if usable_area < 1500:
            return "standard"
        if usable_area < 2500:
            return "large"
        return "xlarge"

    if usable_area < 35:
        return "tiny"
    if usable_area < 55:
        return "compact"
    if usable_area < 80:
        return "standard"
    if usable_area < 120:
        return "large"
    return "xlarge"


def compute_median(values: Iterable[float]) -> float | None:
    numeric = [value for value in values if value is not None and value > 0]
    if not numeric:
        return None
    return float(median(numeric))


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * pct / 100.0) - 1))
    return float(ordered[idx])


@dataclass
class SegmentStats:
    ppm2_median: float | None
    price_median: float | None
    size_median: float | None


WEIGHTS_BY_TYPE = {
    "flat": {
        "ppm2": 0.36,
        "price": 0.16,
        "size": 0.16,
        "affordability": 0.12,
        "features": 0.10,
        "recency": 0.07,
        "drop": 0.03,
    },
    "house": {
        "ppm2": 0.33,
        "price": 0.18,
        "size": 0.18,
        "affordability": 0.12,
        "features": 0.08,
        "recency": 0.07,
        "drop": 0.04,
    },
    "land": {
        "ppm2": 0.40,
        "price": 0.15,
        "size": 0.18,
        "affordability": 0.10,
        "features": 0.07,
        "recency": 0.07,
        "drop": 0.03,
    },
}


@dataclass
class ListingSignals:
    ppm2: float | None
    price_czk: int
    usable_area: float | None
    image_count: int | None
    has_floor_plan: bool
    has_video: bool
    age_hours: float
    price_drop_pct: float


@dataclass
class QualityResult:
    score: float
    reasons: list[str]


def _value_score(value: float | None, median_value: float | None) -> float:
    if value is None or median_value is None or median_value <= 0:
        return 50.0
    diff_pct = (median_value - value) / median_value
    return clamp(50.0 + diff_pct * 140.0, 0.0, 100.0)


def _size_score(size: float | None, median_size: float | None) -> float:
    if size is None or median_size is None or median_size <= 0:
        return 55.0
    deviation = abs(size - median_size) / median_size
    return clamp(100.0 - deviation * 90.0, 0.0, 100.0)


def _affordability_score(price_czk: int, max_price: int) -> float:
    if max_price <= 0:
        return 50.0
    ratio = price_czk / max_price
    return clamp(100.0 - ratio * 80.0, 0.0, 100.0)


def _features_score(image_count: int | None, has_floor_plan: bool, has_video: bool) -> float:
    if image_count is None:
        base = 55.0
    elif image_count >= 12:
        base = 90.0
    elif image_count >= 6:
        base = 80.0
    elif image_count >= 1:
        base = 65.0
    else:
        base = 50.0

    if has_floor_plan:
        base += 6.0
    if has_video:
        base += 6.0
    return clamp(base, 0.0, 100.0)


def _recency_score(age_hours: float) -> float:
    if age_hours <= 0:
        return 100.0
    return clamp(100.0 - age_hours * 1.2, 35.0, 100.0)


def _drop_score(price_drop_pct: float) -> float:
    if price_drop_pct >= 0:
        return 50.0
    return clamp(50.0 + min(abs(price_drop_pct), 25.0) * 2.0, 50.0, 100.0)


def compute_quality(
    estate_type: str,
    signals: ListingSignals,
    stats: SegmentStats,
    max_price: int,
) -> QualityResult:
    weights = WEIGHTS_BY_TYPE.get(estate_type, WEIGHTS_BY_TYPE["flat"])

    ppm2_score = _value_score(signals.ppm2, stats.ppm2_median)
    price_score = _value_score(float(signals.price_czk), stats.price_median)
    size_score = _size_score(signals.usable_area, stats.size_median)
    affordability_score = _affordability_score(signals.price_czk, max_price)
    features_score = _features_score(signals.image_count, signals.has_floor_plan, signals.has_video)
    recency_score = _recency_score(signals.age_hours)
    drop_score = _drop_score(signals.price_drop_pct)

    score = (
        ppm2_score * weights["ppm2"]
        + price_score * weights["price"]
        + size_score * weights["size"]
        + affordability_score * weights["affordability"]
        + features_score * weights["features"]
        + recency_score * weights["recency"]
        + drop_score * weights["drop"]
    )

    reasons: list[str] = []
    if stats.ppm2_median and signals.ppm2 is not None:
        if signals.ppm2 <= stats.ppm2_median * 0.85:
            reasons.append("Price per m2 is well below local median")
        elif signals.ppm2 >= stats.ppm2_median * 1.2:
            reasons.append("Price per m2 is above local median")

    if stats.price_median and signals.price_czk <= stats.price_median * 0.85:
        reasons.append("Total price is meaningfully below segment median")

    if stats.size_median and signals.usable_area is not None:
        if abs(signals.usable_area - stats.size_median) / stats.size_median <= 0.2:
            reasons.append("Size is near the segment sweet spot")

    if signals.price_drop_pct < -5:
        reasons.append("Recent price drop detected")

    if signals.image_count and signals.image_count >= 8:
        reasons.append("Strong listing presentation with many photos")

    return QualityResult(score=clamp(score), reasons=reasons[:3])
