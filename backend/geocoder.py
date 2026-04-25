from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class GeoPoint:
    lat: float
    lon: float


class Geocoder:
    def __init__(self, cache_path: str, user_agent: str, timeout: int = 20) -> None:
        self.cache_path = Path(cache_path)
        self.user_agent = user_agent
        self.timeout = timeout
        self._cache = self._load_cache()
        self._last_call = 0.0

    def _load_cache(self) -> dict[str, dict[str, Any]]:
        if self.cache_path.exists():
            try:
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _normalize_key(query: str) -> str:
        return " ".join(query.lower().split())

    def geocode(self, query: str) -> GeoPoint | None:
        key = self._normalize_key(query)
        cached = self._cache.get(key)
        if cached and cached.get("lat") is not None and cached.get("lon") is not None:
            return GeoPoint(lat=float(cached["lat"]), lon=float(cached["lon"]))
        if cached and cached.get("lat") is None and cached.get("lon") is None:
            return None

        delay = 1.1 - (time.monotonic() - self._last_call)
        if delay > 0:
            time.sleep(delay)

        params = {
            "format": "json",
            "limit": "1",
            "q": query,
        }
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return None

        self._last_call = time.monotonic()
        if not payload:
            self._cache[key] = {"lat": None, "lon": None}
            self._save_cache()
            return None

        try:
            lat = float(payload[0]["lat"])
            lon = float(payload[0]["lon"])
        except (KeyError, ValueError, TypeError):
            return None

        self._cache[key] = {"lat": lat, "lon": lon}
        self._save_cache()
        return GeoPoint(lat=lat, lon=lon)
