from __future__ import annotations

import os
from dataclasses import dataclass


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_optional_int(name: str, default: int | None = None) -> int | None:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return None


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip() in {"1", "true", "True", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    db_path: str = os.getenv("DEALS_DB_PATH", "deals.db")
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = env_int("PORT", 8080)
    sync_interval_hours: int = env_int("SYNC_INTERVAL_HOURS", 12)
    sync_pages: int = env_int("SYNC_PAGES", 14)
    request_timeout_seconds: int = env_int("SREALITY_TIMEOUT_SECONDS", 25)
    use_sample_fallback: bool = env_bool("USE_SAMPLE_FALLBACK", True)
    sync_include_rent: bool = env_bool("SYNC_INCLUDE_RENT", False)
    sync_flat_only: bool = env_bool("SYNC_FLAT_ONLY", True)
    sync_locality_region_id: int | None = env_optional_int("SYNC_LOCALITY_REGION_ID", 5)
