from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class AreaMatch:
    group: str
    confidence: float


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower().strip()
    return re.sub(r"\s+", " ", lowered)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c


JIZERSKE_HINTS = (
    "bedrichov",
    "jizerske",
    "jizerou",
    "jablonec nad nisou",
    "liberec",
    "smrzovka",
    "tanvald",
    "josefuv dul",
    "desna",
    "hejnice",
    "frydlant",
    "harrachov",
    "korenov",
    "albrechtice",
    "janov nad nisou",
)

KRKONOSE_HINTS = (
    "spindleruv mlyn",
    "pec pod snezkou",
    "harrachov",
    "rokynice nad jizerou",
    "vrchlabi",
    "janske lazne",
    "horni marsov",
    "dolni dvur",
    "benecko",
    "cerny dul",
    "herlikovice",
)

ORLICKE_HINTS = (
    "destne",
    "orlicke",
    "orlicke hory",
    "rihno",
    "rychnov nad kneznou",
    "orlice",
    "zamberk",
    "kunvald",
    "kraliky",
    "mihulovice",
)

JIZERSKE_BBOX = (50.68, 50.92, 14.90, 15.45)
KRKONOSE_BBOX = (50.50, 50.85, 15.35, 16.20)
ORLICKE_BBOX = (50.10, 50.40, 16.15, 16.90)

PRAGUE_REGION_ID = 10
STREDOCESKY_REGION_ID = 11


def _bbox_contains(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> bool:
    lat_min, lat_max, lon_min, lon_max = bbox
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def _match_by_hints(locality: str, hints: Iterable[str]) -> bool:
    normalized = normalize_text(locality)
    return any(hint in normalized for hint in hints)


def classify_area(
    locality: str,
    region_id: int | None,
    lat: float | None,
    lon: float | None,
) -> AreaMatch | None:
    if region_id == PRAGUE_REGION_ID:
        return AreaMatch("prague", 1.0)
    if region_id == STREDOCESKY_REGION_ID:
        return AreaMatch("stredocesky", 1.0)

    if _match_by_hints(locality, JIZERSKE_HINTS):
        return AreaMatch("jizerske", 0.9)
    if _match_by_hints(locality, KRKONOSE_HINTS):
        return AreaMatch("krkonose", 0.9)
    if _match_by_hints(locality, ORLICKE_HINTS):
        return AreaMatch("orlicke", 0.9)

    if lat is not None and lon is not None:
        if _bbox_contains(lat, lon, JIZERSKE_BBOX):
            return AreaMatch("jizerske", 0.8)
        if _bbox_contains(lat, lon, KRKONOSE_BBOX):
            return AreaMatch("krkonose", 0.8)
        if _bbox_contains(lat, lon, ORLICKE_BBOX):
            return AreaMatch("orlicke", 0.8)

    return None
