from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import Database
from .geography import (
    distance_to_bedrichov,
    is_bedrichov_locality,
    is_jizerske_hory_locality,
)
from .scoring import build_segment_key, compute_median, deal_from_median, slugify_locality
from .sreality_client import ListingRecord, SrealityClient, normalize_listing

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime(ISO_FORMAT)


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


class DealsService:
    def __init__(
        self,
        db: Database,
        client: SrealityClient,
        default_include_rent: bool = True,
        default_locality_region_id: int | None = None,
        default_flat_only: bool = False,
    ) -> None:
        self.db = db
        self.client = client
        self.default_include_rent = default_include_rent
        self.default_locality_region_id = default_locality_region_id
        self.default_flat_only = default_flat_only

    def run_sync(
        self,
        max_pages: int = 4,
        include_rent: bool | None = None,
        locality_region_id: int | None = None,
        flat_only: bool | None = None,
    ) -> dict[str, Any]:
        started_at = utc_now()
        run_id = self._start_sync_run(started_at)
        fetched_count = 0
        stored_count = 0

        include_rent_resolved = (
            self.default_include_rent if include_rent is None else include_rent
        )
        locality_region_id_resolved = (
            self.default_locality_region_id
            if locality_region_id is None
            else locality_region_id
        )
        flat_only_resolved = self.default_flat_only if flat_only is None else flat_only

        try:
            category_types = [1, 2] if include_rent_resolved else [1]
            records: list[ListingRecord] = []

            for category_type in category_types:
                for page in range(1, max_pages + 1):
                    payload = self.client.fetch_page(
                        page=page,
                        per_page=60,
                        category_type_cb=category_type,
                        category_main_cb=1 if flat_only_resolved else None,
                        locality_region_id=locality_region_id_resolved,
                    )
                    items = self._extract_estates(payload)
                    if not items:
                        break

                    fetched_count += len(items)
                    parsed_any = False
                    for item in items:
                        parsed = normalize_listing(item, category_type_cb=category_type)
                        if parsed:
                            records.append(parsed)
                            parsed_any = True

                    if not parsed_any:
                        break

                    result_size = payload.get("result_size")
                    if isinstance(result_size, int) and page * 60 >= result_size:
                        break

            stored_count = self._upsert_records(records)
            self.recalculate_deal_scores()
            self._enforce_active_scope(
                include_rent=include_rent_resolved,
                flat_only=flat_only_resolved,
                locality_region_id=locality_region_id_resolved,
            )
            self._finish_sync_run(
                run_id,
                status="ok",
                finished_at=utc_now(),
                fetched_count=fetched_count,
                stored_count=stored_count,
            )
            return {
                "status": "ok",
                "fetched_count": fetched_count,
                "stored_count": stored_count,
                "started_at": started_at,
                "finished_at": utc_now(),
            }
        except Exception as exc:
            self._finish_sync_run(
                run_id,
                status="error",
                finished_at=utc_now(),
                fetched_count=fetched_count,
                stored_count=stored_count,
                error_text=str(exc),
            )
            raise

    def _enforce_active_scope(
        self,
        include_rent: bool,
        flat_only: bool,
        locality_region_id: int | None,
    ) -> None:
        if locality_region_id != 5:
            return

        allowed_categories = ["sale", "rent"] if include_rent else ["sale"]
        placeholders = ",".join("?" for _ in allowed_categories)

        if flat_only:
            self.db.execute(
                f"""
                UPDATE listings
                SET is_active = CASE
                    WHEN is_jizerske_hory = 1
                         AND estate_type = 'flat'
                         AND category_type IN ({placeholders})
                    THEN 1
                    ELSE 0
                END
                """,
                tuple(allowed_categories),
            )
            return

        self.db.execute(
            f"""
            UPDATE listings
            SET is_active = CASE
                WHEN is_jizerske_hory = 1
                     AND category_type IN ({placeholders})
                THEN 1
                ELSE 0
            END
            """,
            tuple(allowed_categories),
        )

    def load_fixture_file(self, fixture_path: str) -> int:
        fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        items = self._extract_estates(fixture)
        records = [normalize_listing(item) for item in items]
        return self._upsert_records([record for record in records if record])

    @staticmethod
    def _extract_estates(payload: dict[str, Any]) -> list[dict[str, Any]]:
        embedded = payload.get("_embedded")
        if isinstance(embedded, dict):
            estates = embedded.get("estates")
            if isinstance(estates, list):
                return [x for x in estates if isinstance(x, dict)]

        if isinstance(payload.get("estates"), list):
            return [x for x in payload["estates"] if isinstance(x, dict)]

        return []

    def _start_sync_run(self, started_at: str) -> int:
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO sync_runs(started_at, status)
                VALUES (?, ?)
                """,
                (started_at, "running"),
            )
            return int(cursor.lastrowid)

    def _finish_sync_run(
        self,
        run_id: int,
        status: str,
        finished_at: str,
        fetched_count: int,
        stored_count: int,
        error_text: str | None = None,
    ) -> None:
        self.db.execute(
            """
            UPDATE sync_runs
            SET status = ?, finished_at = ?, fetched_count = ?, stored_count = ?, error_text = ?
            WHERE id = ?
            """,
            (status, finished_at, fetched_count, stored_count, error_text, run_id),
        )

    def _upsert_records(self, records: list[ListingRecord]) -> int:
        stored = 0
        now = utc_now()

        with self.db.connection() as conn:
            for record in records:
                existing = conn.execute(
                    "SELECT id, price_czk FROM listings WHERE external_id = ?",
                    (record.external_id,),
                ).fetchone()

                distance_km = distance_to_bedrichov(record.lat, record.lon)
                is_target = 1 if is_jizerske_hory_locality(record.locality, record.lat, record.lon) else 0

                conn.execute(
                    """
                    INSERT INTO listings (
                        external_id, url, title, locality, locality_slug,
                        category_type, estate_type, disposition, usable_area,
                        price_czk, currency, price_per_m2, lat, lon, image_url,
                        distance_to_bedrichov_km, is_jizerske_hory,
                        first_seen, last_seen, source_payload, is_active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(external_id) DO UPDATE SET
                        url = excluded.url,
                        title = excluded.title,
                        locality = excluded.locality,
                        locality_slug = excluded.locality_slug,
                        category_type = excluded.category_type,
                        estate_type = excluded.estate_type,
                        disposition = excluded.disposition,
                        usable_area = excluded.usable_area,
                        price_czk = excluded.price_czk,
                        currency = excluded.currency,
                        price_per_m2 = excluded.price_per_m2,
                        lat = excluded.lat,
                        lon = excluded.lon,
                        image_url = excluded.image_url,
                        distance_to_bedrichov_km = excluded.distance_to_bedrichov_km,
                        is_jizerske_hory = excluded.is_jizerske_hory,
                        last_seen = excluded.last_seen,
                        source_payload = excluded.source_payload,
                        is_active = 1
                    """,
                    (
                        record.external_id,
                        record.url,
                        record.title,
                        record.locality,
                        record.locality_slug,
                        record.category_type,
                        record.estate_type,
                        record.disposition,
                        record.usable_area,
                        record.price_czk,
                        record.currency,
                        record.price_per_m2,
                        record.lat,
                        record.lon,
                        record.image_url,
                        distance_km,
                        is_target,
                        now,
                        now,
                        record.source_payload,
                    ),
                )

                listing_row = conn.execute(
                    "SELECT id, price_czk FROM listings WHERE external_id = ?",
                    (record.external_id,),
                ).fetchone()
                if listing_row is None:
                    continue

                should_record_history = (
                    existing is None or int(existing["price_czk"]) != record.price_czk
                )
                if should_record_history:
                    conn.execute(
                        """
                        INSERT INTO price_history(listing_id, observed_at, price_czk, price_per_m2)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            int(listing_row["id"]),
                            now,
                            record.price_czk,
                            record.price_per_m2,
                        ),
                    )

                stored += 1

        return stored

    @staticmethod
    def _attractiveness_tier(score: float) -> str:
        if score >= 84:
            return "Exceptional"
        if score >= 72:
            return "Strong"
        if score >= 58:
            return "Promising"
        if score >= 45:
            return "Watch"
        return "Weak"

    @staticmethod
    def _compute_attractiveness(
        locality: str,
        deal_score: float | None,
        distance_km: float | None,
        usable_area: float | None,
        is_target_area: bool,
        price_change_pct: float,
    ) -> tuple[float, str, list[str]]:
        if deal_score is None:
            price_component = 50.0
        else:
            price_component = clamp(50.0 + deal_score * 1.6, 0.0, 100.0)

        if distance_km is None:
            distance_component = 35.0
        else:
            distance_component = clamp(100.0 - distance_km * 3.2, 0.0, 100.0)

        if usable_area is None:
            size_component = 55.0
        else:
            size_component = clamp(100.0 - abs(usable_area - 65.0) * 1.5, 0.0, 100.0)

        target_bonus = 10.0 if is_target_area else -18.0
        bedrichov_bonus = 8.0 if is_bedrichov_locality(locality) else 0.0
        drop_bonus = clamp(-price_change_pct * 1.4, 0.0, 8.0)

        final_score = clamp(
            0.45 * price_component
            + 0.35 * distance_component
            + 0.20 * size_component
            + target_bonus
            + bedrichov_bonus
            + drop_bonus,
            0.0,
            100.0,
        )

        reasons: list[str] = []
        if is_bedrichov_locality(locality):
            reasons.append("Directly in Bedrichov")
        elif distance_km is not None:
            if distance_km <= 8:
                reasons.append(f"Only {distance_km:.1f} km from Bedrichov")
            else:
                reasons.append(f"{distance_km:.1f} km from Bedrichov")

        if deal_score is not None:
            if deal_score >= 15:
                reasons.append("Price per m2 is far below local market median")
            elif deal_score >= 5:
                reasons.append("Price per m2 is below local market median")
            elif deal_score <= -10:
                reasons.append("Price per m2 is above local market median")

        if is_target_area:
            reasons.append("Inside the Jizerske hory target area")
        else:
            reasons.append("Outside the Jizerske hory target area")

        if usable_area is not None and 45 <= usable_area <= 95:
            reasons.append("Practical flat size for year-round use")

        if price_change_pct <= -5:
            reasons.append("Recent price drop detected")

        tier = DealsService._attractiveness_tier(final_score)
        return final_score, tier, reasons[:3]

    def recalculate_deal_scores(self) -> None:
        rows = self.db.fetchall(
            """
            SELECT
                id,
                category_type,
                estate_type,
                locality,
                locality_slug,
                disposition,
                usable_area,
                price_per_m2,
                lat,
                lon,
                distance_to_bedrichov_km,
                is_jizerske_hory
            FROM listings
            WHERE is_active = 1
            """
        )

        exact_groups: dict[str, list[float]] = defaultdict(list)
        local_groups: dict[str, list[float]] = defaultdict(list)
        broad_groups: dict[str, list[float]] = defaultdict(list)

        for row in rows:
            ppm2 = row["price_per_m2"]
            if not ppm2:
                continue

            key = build_segment_key(
                category_type=row["category_type"] or "unknown",
                estate_type=row["estate_type"] or "unknown",
                locality_slug=row["locality_slug"] or "unknown",
                disposition=row["disposition"] or "unknown",
                usable_area=row["usable_area"],
            )
            local = "|".join(
                [
                    row["category_type"] or "unknown",
                    row["estate_type"] or "unknown",
                    row["locality_slug"] or "unknown",
                ]
            )
            broad = "|".join([row["category_type"] or "unknown", row["estate_type"] or "unknown"])

            exact_groups[key].append(float(ppm2))
            local_groups[local].append(float(ppm2))
            broad_groups[broad].append(float(ppm2))

        exact_medians = {k: compute_median(v) for k, v in exact_groups.items()}
        local_medians = {k: compute_median(v) for k, v in local_groups.items()}
        broad_medians = {k: compute_median(v) for k, v in broad_groups.items()}

        trends = {
            int(row["listing_id"]): float(row["price_change_pct"] or 0)
            for row in self.db.fetchall(
                """
                SELECT
                    ph.listing_id,
                    CASE
                        WHEN MAX(ph.price_czk) > 0
                        THEN ((MIN(ph.price_czk) - MAX(ph.price_czk)) * 100.0) / MAX(ph.price_czk)
                        ELSE 0
                    END AS price_change_pct
                FROM price_history ph
                GROUP BY ph.listing_id
                """
            )
        }

        updates: list[tuple[Any, ...]] = []

        for row in rows:
            listing_id = int(row["id"])
            segment_key = build_segment_key(
                category_type=row["category_type"] or "unknown",
                estate_type=row["estate_type"] or "unknown",
                locality_slug=row["locality_slug"] or "unknown",
                disposition=row["disposition"] or "unknown",
                usable_area=row["usable_area"],
            )
            local = "|".join(
                [
                    row["category_type"] or "unknown",
                    row["estate_type"] or "unknown",
                    row["locality_slug"] or "unknown",
                ]
            )
            broad = "|".join([row["category_type"] or "unknown", row["estate_type"] or "unknown"])

            reference = (
                exact_medians.get(segment_key)
                or local_medians.get(local)
                or broad_medians.get(broad)
            )

            score, bucket = deal_from_median(row["price_per_m2"], reference)

            distance_km = row["distance_to_bedrichov_km"]
            if distance_km is None and row["lat"] is not None and row["lon"] is not None:
                distance_km = distance_to_bedrichov(float(row["lat"]), float(row["lon"]))

            locality = str(row["locality"] or "")
            is_target_area = bool(row["is_jizerske_hory"]) or is_jizerske_hory_locality(
                locality,
                row["lat"],
                row["lon"],
            )

            attractiveness_score, attractiveness_tier, reasons = self._compute_attractiveness(
                locality=locality,
                deal_score=score,
                distance_km=float(distance_km) if distance_km is not None else None,
                usable_area=row["usable_area"],
                is_target_area=is_target_area,
                price_change_pct=trends.get(listing_id, 0.0),
            )

            updates.append(
                (
                    segment_key,
                    score,
                    bucket,
                    float(distance_km) if distance_km is not None else None,
                    1 if is_target_area else 0,
                    attractiveness_score,
                    attractiveness_tier,
                    json.dumps(reasons, ensure_ascii=False),
                    listing_id,
                )
            )

        if updates:
            self.db.executemany(
                """
                UPDATE listings
                SET
                    segment_key = ?,
                    deal_score = ?,
                    deal_bucket = ?,
                    distance_to_bedrichov_km = ?,
                    is_jizerske_hory = ?,
                    attractiveness_score = ?,
                    attractiveness_tier = ?,
                    attractiveness_reasons = ?
                WHERE id = ?
                """,
                updates,
            )

    def list_listings(self, filters: dict[str, str]) -> dict[str, Any]:
        where: list[str] = ["l.is_active = 1"]
        params: list[Any] = []

        q = (filters.get("q") or "").strip()
        if q:
            where.append("(l.title LIKE ? OR l.locality LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%"])

        locality = (filters.get("locality") or "").strip()
        if locality:
            where.append("(l.locality_slug = ? OR l.locality = ?)")
            params.extend([slugify_locality(locality), locality])

        deal_bucket = (filters.get("deal_bucket") or "").strip()
        if deal_bucket:
            buckets = [chunk.strip() for chunk in deal_bucket.split(",") if chunk.strip()]
            placeholders = ",".join("?" for _ in buckets)
            where.append(f"l.deal_bucket IN ({placeholders})")
            params.extend(buckets)

        attractiveness_tier = (filters.get("attractiveness_tier") or "").strip()
        if attractiveness_tier:
            tiers = [chunk.strip() for chunk in attractiveness_tier.split(",") if chunk.strip()]
            placeholders = ",".join("?" for _ in tiers)
            where.append(f"l.attractiveness_tier IN ({placeholders})")
            params.extend(tiers)

        disposition = (filters.get("disposition") or "").strip()
        if disposition:
            where.append("l.disposition = ?")
            params.append(disposition)

        estate_type = (filters.get("estate_type") or "").strip()
        if estate_type:
            where.append("l.estate_type = ?")
            params.append(estate_type)

        category_type = (filters.get("category_type") or "").strip()
        if category_type:
            where.append("l.category_type = ?")
            params.append(category_type)

        focus_area = (filters.get("focus_area") or "").strip()
        if focus_area == "1":
            where.append("l.is_jizerske_hory = 1")

        min_price = (filters.get("min_price") or "").strip()
        if min_price.isdigit():
            where.append("l.price_czk >= ?")
            params.append(int(min_price))

        max_price = (filters.get("max_price") or "").strip()
        if max_price.isdigit():
            where.append("l.price_czk <= ?")
            params.append(int(max_price))

        min_area = (filters.get("min_area") or "").strip()
        if min_area:
            try:
                where.append("COALESCE(l.usable_area, 0) >= ?")
                params.append(float(min_area))
            except ValueError:
                pass

        max_area = (filters.get("max_area") or "").strip()
        if max_area:
            try:
                where.append("COALESCE(l.usable_area, 0) <= ?")
                params.append(float(max_area))
            except ValueError:
                pass

        max_distance_km = (filters.get("max_distance_km") or "").strip()
        if max_distance_km:
            try:
                where.append("COALESCE(l.distance_to_bedrichov_km, 9999) <= ?")
                params.append(float(max_distance_km))
            except ValueError:
                pass

        min_attractiveness = (filters.get("min_attractiveness") or "").strip()
        if min_attractiveness:
            try:
                where.append("COALESCE(l.attractiveness_score, 0) >= ?")
                params.append(float(min_attractiveness))
            except ValueError:
                pass

        saved_only = (filters.get("saved_only") or "").strip() == "1"
        if saved_only:
            where.append("w.external_id IS NOT NULL")

        sort_map = {
            "attractiveness": "l.attractiveness_score",
            "deal": "l.deal_score",
            "distance": "l.distance_to_bedrichov_km",
            "price": "l.price_czk",
            "ppm2": "l.price_per_m2",
            "fresh": "l.last_seen",
            "drop": "price_change_pct",
        }
        sort_by = sort_map.get((filters.get("sort") or "attractiveness").strip(), "l.attractiveness_score")
        order = "ASC" if (filters.get("order") or "desc").strip().lower() == "asc" else "DESC"

        limit = filters.get("limit") or "40"
        offset = filters.get("offset") or "0"
        limit_n = min(max(int(limit) if str(limit).isdigit() else 40, 1), 200)
        offset_n = max(int(offset) if str(offset).isdigit() else 0, 0)

        where_sql = " AND ".join(where)

        base_sql = f"""
            FROM listings l
            LEFT JOIN watchlist w ON w.external_id = l.external_id
            LEFT JOIN (
                SELECT
                    ph.listing_id,
                    MIN(ph.price_czk) AS min_price,
                    MAX(ph.price_czk) AS max_price,
                    CASE
                        WHEN MAX(ph.price_czk) > 0
                        THEN ((MIN(ph.price_czk) - MAX(ph.price_czk)) * 100.0) / MAX(ph.price_czk)
                        ELSE 0
                    END AS price_change_pct
                FROM price_history ph
                GROUP BY ph.listing_id
            ) trends ON trends.listing_id = l.id
            WHERE {where_sql}
        """

        total_row = self.db.fetchone(f"SELECT COUNT(*) AS count {base_sql}", tuple(params))
        total = int(total_row["count"]) if total_row else 0

        rows = self.db.fetchall(
            f"""
            SELECT
                l.external_id,
                l.url,
                l.title,
                l.locality,
                l.locality_slug,
                l.category_type,
                l.estate_type,
                l.disposition,
                l.usable_area,
                l.price_czk,
                l.currency,
                l.price_per_m2,
                l.lat,
                l.lon,
                l.image_url,
                l.deal_score,
                l.deal_bucket,
                l.distance_to_bedrichov_km,
                l.is_jizerske_hory,
                l.attractiveness_score,
                l.attractiveness_tier,
                l.attractiveness_reasons,
                l.first_seen,
                l.last_seen,
                COALESCE(trends.price_change_pct, 0) AS price_change_pct,
                CASE WHEN w.external_id IS NULL THEN 0 ELSE 1 END AS is_saved
            {base_sql}
            ORDER BY {sort_by} {order}, l.last_seen DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params + [limit_n, offset_n]),
        )

        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            reasons_raw = item.get("attractiveness_reasons")
            if isinstance(reasons_raw, str) and reasons_raw.strip():
                try:
                    parsed = json.loads(reasons_raw)
                    item["attractiveness_reasons"] = parsed if isinstance(parsed, list) else []
                except json.JSONDecodeError:
                    item["attractiveness_reasons"] = []
            else:
                item["attractiveness_reasons"] = []
            item["is_jizerske_hory"] = int(item.get("is_jizerske_hory") or 0)
            items.append(item)

        return {
            "total": total,
            "items": items,
            "limit": limit_n,
            "offset": offset_n,
        }

    def list_filters(self) -> dict[str, Any]:
        localities = [
            dict(row)
            for row in self.db.fetchall(
                """
                SELECT locality_slug, MIN(locality) AS locality, COUNT(*) AS count
                FROM listings
                WHERE is_active = 1
                GROUP BY locality_slug
                ORDER BY count DESC, locality ASC
                LIMIT 120
                """
            )
        ]

        dispositions = [
            row["disposition"]
            for row in self.db.fetchall(
                """
                SELECT disposition
                FROM listings
                WHERE is_active = 1
                GROUP BY disposition
                ORDER BY COUNT(*) DESC
                LIMIT 20
                """
            )
            if row["disposition"]
        ]

        estate_types = [
            row["estate_type"]
            for row in self.db.fetchall(
                """
                SELECT estate_type
                FROM listings
                WHERE is_active = 1
                GROUP BY estate_type
                ORDER BY COUNT(*) DESC
                """
            )
            if row["estate_type"]
        ]

        category_types = [
            row["category_type"]
            for row in self.db.fetchall(
                """
                SELECT category_type
                FROM listings
                WHERE is_active = 1
                GROUP BY category_type
                ORDER BY COUNT(*) DESC
                """
            )
            if row["category_type"]
        ]

        buckets = [
            row["deal_bucket"]
            for row in self.db.fetchall(
                """
                SELECT deal_bucket
                FROM listings
                WHERE is_active = 1
                GROUP BY deal_bucket
                ORDER BY COUNT(*) DESC
                """
            )
            if row["deal_bucket"]
        ]

        attractiveness_tiers = [
            row["attractiveness_tier"]
            for row in self.db.fetchall(
                """
                SELECT attractiveness_tier
                FROM listings
                WHERE is_active = 1
                GROUP BY attractiveness_tier
                ORDER BY
                    CASE attractiveness_tier
                        WHEN 'Exceptional' THEN 1
                        WHEN 'Strong' THEN 2
                        WHEN 'Promising' THEN 3
                        WHEN 'Watch' THEN 4
                        WHEN 'Weak' THEN 5
                        ELSE 6
                    END
                """
            )
            if row["attractiveness_tier"]
        ]

        return {
            "localities": localities,
            "dispositions": dispositions,
            "estate_types": estate_types,
            "category_types": category_types,
            "deal_buckets": buckets,
            "attractiveness_tiers": attractiveness_tiers,
        }

    def stats(self) -> dict[str, Any]:
        counts = {
            row["deal_bucket"] or "Unknown": int(row["count"])
            for row in self.db.fetchall(
                """
                SELECT deal_bucket, COUNT(*) AS count
                FROM listings
                WHERE is_active = 1
                GROUP BY deal_bucket
                """
            )
        }

        tier_counts = {
            row["attractiveness_tier"] or "Unknown": int(row["count"])
            for row in self.db.fetchall(
                """
                SELECT attractiveness_tier, COUNT(*) AS count
                FROM listings
                WHERE is_active = 1
                GROUP BY attractiveness_tier
                """
            )
        }

        totals = self.db.fetchone(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN is_jizerske_hory = 1 THEN 1 ELSE 0 END) AS jizerske_total,
                SUM(CASE WHEN distance_to_bedrichov_km <= 8 THEN 1 ELSE 0 END) AS bedrichov_near,
                AVG(price_czk) AS avg_price,
                AVG(price_per_m2) AS avg_ppm2,
                AVG(attractiveness_score) AS avg_attractiveness,
                MAX(last_seen) AS latest_seen
            FROM listings
            WHERE is_active = 1
            """
        )

        sync = self.db.fetchone(
            """
            SELECT started_at, finished_at, status, fetched_count, stored_count, error_text
            FROM sync_runs
            ORDER BY id DESC
            LIMIT 1
            """
        )

        watchlist_count = self.db.fetchone("SELECT COUNT(*) AS count FROM watchlist")

        top_rows = self.db.fetchall(
            """
            SELECT
                external_id,
                title,
                locality,
                price_czk,
                distance_to_bedrichov_km,
                attractiveness_score,
                attractiveness_tier,
                deal_bucket,
                url
            FROM listings
            WHERE is_active = 1
              AND category_type = 'sale'
              AND estate_type = 'flat'
              AND is_jizerske_hory = 1
            ORDER BY COALESCE(attractiveness_score, 0) DESC, COALESCE(deal_score, -999) DESC
            LIMIT 4
            """
        )

        top_picks = [dict(row) for row in top_rows]

        return {
            "total_listings": int(totals["total"] or 0) if totals else 0,
            "jizerske_total": int(totals["jizerske_total"] or 0) if totals else 0,
            "bedrichov_near": int(totals["bedrichov_near"] or 0) if totals else 0,
            "avg_price": float(totals["avg_price"] or 0) if totals else 0,
            "avg_price_per_m2": float(totals["avg_ppm2"] or 0) if totals else 0,
            "avg_attractiveness": float(totals["avg_attractiveness"] or 0) if totals else 0,
            "latest_seen": totals["latest_seen"] if totals else None,
            "by_bucket": counts,
            "by_attractiveness": tier_counts,
            "top_picks": top_picks,
            "watchlist_count": int(watchlist_count["count"] or 0) if watchlist_count else 0,
            "last_sync": dict(sync) if sync else None,
        }

    def list_watchlist(self) -> list[dict[str, Any]]:
        rows = self.db.fetchall(
            """
            SELECT
                w.external_id,
                w.note,
                w.created_at,
                l.title,
                l.price_czk,
                l.locality,
                l.attractiveness_tier,
                l.deal_bucket
            FROM watchlist w
            LEFT JOIN listings l ON l.external_id = w.external_id
            ORDER BY w.created_at DESC
            """
        )
        return [dict(row) for row in rows]

    def save_watchlist(self, external_id: str, note: str | None = None) -> None:
        self.db.execute(
            """
            INSERT INTO watchlist(external_id, note, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(external_id) DO UPDATE SET note = excluded.note
            """,
            (external_id, (note or "").strip() or None, utc_now()),
        )

    def remove_watchlist(self, external_id: str) -> None:
        self.db.execute("DELETE FROM watchlist WHERE external_id = ?", (external_id,))
