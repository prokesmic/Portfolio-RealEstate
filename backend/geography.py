from __future__ import annotations

import math
import re
import unicodedata

BEDRICHOV_LAT = 50.7914
BEDRICHOV_LON = 15.1426

LIBERECKY_REGION_ID = 5

JIZERSKE_LOCALITY_HINTS = (
    "bedrichov",
    "janov nad nisou",
    "hrabetice",
    "jizerske",
    "jizerou",
    "jizerskych",
    "jablonec nad nisou",
    "liberec",
    "smrzovka",
    "tanvald",
    "josefuv dul",
    "desna",
    "hejnice",
    "oldrichov v hajich",
    "raspenava",
    "frydlant",
    "harrachov",
    "korenov",
    "polubny",
    "kozlov",
    "albrechtice",
)


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


def distance_to_bedrichov(lat: float | None, lon: float | None) -> float | None:
    if lat is None or lon is None:
        return None
    return haversine_km(lat, lon, BEDRICHOV_LAT, BEDRICHOV_LON)


def is_bedrichov_locality(locality: str) -> bool:
    return "bedrichov" in normalize_text(locality)


def is_jizerske_hory_locality(locality: str, lat: float | None = None, lon: float | None = None) -> bool:
    normalized = normalize_text(locality)
    if any(hint in normalized for hint in JIZERSKE_LOCALITY_HINTS):
        return True

    distance = distance_to_bedrichov(lat, lon)
    return bool(distance is not None and distance <= 28.0)
