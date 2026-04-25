from __future__ import annotations

import re
import unicodedata
from statistics import median
from typing import Iterable


def slugify_locality(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", (value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"\s+", " ", ascii_text.strip().lower())
    return re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")


def area_bucket(usable_area: float | None) -> str:
    if usable_area is None:
        return "unknown"
    if usable_area < 35:
        return "tiny"
    if usable_area < 55:
        return "compact"
    if usable_area < 80:
        return "standard"
    if usable_area < 120:
        return "large"
    return "xlarge"


def build_segment_key(
    category_type: str,
    estate_type: str,
    locality_slug: str,
    disposition: str,
    usable_area: float | None,
) -> str:
    return "|".join(
        [
            category_type or "unknown",
            estate_type or "unknown",
            locality_slug or "unknown",
            disposition or "unknown",
            area_bucket(usable_area),
        ]
    )


def compute_median(values: Iterable[float]) -> float | None:
    numeric = [value for value in values if value and value > 0]
    if not numeric:
        return None
    return float(median(numeric))


def deal_from_median(price_per_m2: float | None, reference_median: float | None) -> tuple[float | None, str]:
    if not price_per_m2 or not reference_median:
        return None, "Unknown"

    diff_pct = ((price_per_m2 - reference_median) / reference_median) * 100.0
    score = -diff_pct

    if diff_pct <= -25:
        return score, "Jackpot"
    if diff_pct <= -12:
        return score, "Great"
    if diff_pct <= 8:
        return score, "Fair"
    if diff_pct <= 22:
        return score, "High"
    return score, "Premium"
