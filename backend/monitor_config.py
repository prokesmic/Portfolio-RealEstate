from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list_int(name: str, default: Iterable[int]) -> list[int]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return list(default)
    values: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            values.append(int(token))
        except ValueError:
            continue
    return values or list(default)


@dataclass(frozen=True)
class MonitorConfig:
    source_provider: str = os.getenv("SOURCE_PROVIDER", "sreality").strip().lower()
    supabase_url: str = os.getenv("SUPABASE_URL", "").strip()
    supabase_service_key: str = os.getenv("SUPABASE_SERVICE_KEY", "").strip()

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    telegram_enabled: bool = env_bool("TELEGRAM_ENABLED", True)

    sync_interval_minutes: int = env_int("SYNC_INTERVAL_MINUTES", 30)
    sync_pages: int = env_int("SYNC_PAGES", 14)
    request_timeout_seconds: int = env_int("SREALITY_TIMEOUT_SECONDS", 25)

    max_price_czk: int = env_int("MAX_PRICE_CZK", 15_000_000)
    region_ids: list[int] = field(
        default_factory=lambda: env_list_int("SYNC_REGION_IDS", [10, 11, 5, 6, 7])
    )
    estate_type_cbs: list[int] = field(
        default_factory=lambda: env_list_int("SYNC_ESTATE_TYPE_CBS", [1, 2, 3])
    )

    geocode_cache_path: str = os.getenv(
        "GEOCODE_CACHE_PATH", "data/geocode_cache.json"
    )
    nominatim_user_agent: str = os.getenv(
        "NOMINATIM_USER_AGENT", "sreality-monitor/1.0 (contact: you@example.com)"
    )
    geocode_max_per_run: int = env_int("GEOCODE_MAX_PER_RUN", 40)

    def validate(self) -> None:
        if self.source_provider != "sreality":
            raise ValueError(f"Unsupported SOURCE_PROVIDER: {self.source_provider}")
        if not self.supabase_url or not self.supabase_service_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY are required")
