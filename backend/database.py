from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.RLock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def connection(self) -> Iterable[sqlite3.Connection]:
        with self._lock:
            connection = self._connect()
            try:
                yield connection
                connection.commit()
            finally:
                connection.close()

    def _initialize(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    external_id TEXT NOT NULL UNIQUE,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    locality TEXT,
                    locality_slug TEXT,
                    category_type TEXT,
                    estate_type TEXT,
                    disposition TEXT,
                    usable_area REAL,
                    price_czk INTEGER NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'CZK',
                    price_per_m2 REAL,
                    lat REAL,
                    lon REAL,
                    image_url TEXT,
                    segment_key TEXT,
                    deal_score REAL,
                    deal_bucket TEXT,
                    distance_to_bedrichov_km REAL,
                    is_jizerske_hory INTEGER NOT NULL DEFAULT 0,
                    attractiveness_score REAL,
                    attractiveness_tier TEXT,
                    attractiveness_reasons TEXT,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    source_payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    listing_id INTEGER NOT NULL,
                    observed_at TEXT NOT NULL,
                    price_czk INTEGER NOT NULL,
                    price_per_m2 REAL,
                    FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    fetched_count INTEGER NOT NULL DEFAULT 0,
                    stored_count INTEGER NOT NULL DEFAULT 0,
                    error_text TEXT
                );

                CREATE TABLE IF NOT EXISTS watchlist (
                    external_id TEXT PRIMARY KEY,
                    note TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_listings_locality ON listings(locality_slug);
                CREATE INDEX IF NOT EXISTS idx_listings_bucket ON listings(deal_bucket);
                CREATE INDEX IF NOT EXISTS idx_history_listing_time ON price_history(listing_id, observed_at);
                """
            )
            self._migrate_listings_columns(conn)
            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_listings_jizerske ON listings(is_jizerske_hory);
                CREATE INDEX IF NOT EXISTS idx_listings_attractiveness ON listings(attractiveness_score);
                """
            )

    @staticmethod
    def _migrate_listings_columns(conn: sqlite3.Connection) -> None:
        existing = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(listings)").fetchall()
        }
        required: dict[str, str] = {
            "distance_to_bedrichov_km": "ALTER TABLE listings ADD COLUMN distance_to_bedrichov_km REAL",
            "is_jizerske_hory": "ALTER TABLE listings ADD COLUMN is_jizerske_hory INTEGER NOT NULL DEFAULT 0",
            "attractiveness_score": "ALTER TABLE listings ADD COLUMN attractiveness_score REAL",
            "attractiveness_tier": "ALTER TABLE listings ADD COLUMN attractiveness_tier TEXT",
            "attractiveness_reasons": "ALTER TABLE listings ADD COLUMN attractiveness_reasons TEXT",
        }
        for name, statement in required.items():
            if name not in existing:
                conn.execute(statement)

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self.connection() as conn:
            conn.execute(sql, params)

    def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        if not rows:
            return
        with self.connection() as conn:
            conn.executemany(sql, rows)

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self.connection() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchall()

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self.connection() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchone()
