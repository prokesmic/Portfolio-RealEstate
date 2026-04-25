from __future__ import annotations

import json
import math
import ssl
import statistics
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.sreality_client import SrealityClient, normalize_listing

SEED_PATH = ROOT / "data" / "portfolio_seed.json"
OUTPUT_PATH = ROOT / "dashboard" / "data" / "portfolio_snapshot.json"
OUTPUT_JS_PATH = ROOT / "dashboard" / "data" / "portfolio_snapshot.js"
GEOCODE_CACHE_PATH = ROOT / "data" / "portfolio_geocode_cache.json"
USER_AGENT = "Codex Portfolio Snapshot/1.0"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_snapshot_js(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "window.__PORTFOLIO_SNAPSHOT__ = "
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )


def slugify(text: str) -> str:
    return (
        text.lower()
        .replace("ř", "r")
        .replace("ž", "z")
        .replace("š", "s")
        .replace("č", "c")
        .replace("ě", "e")
        .replace("ý", "y")
        .replace("á", "a")
        .replace("í", "i")
        .replace("é", "e")
        .replace("ů", "u")
        .replace("ú", "u")
        .replace("ň", "n")
        .replace("ť", "t")
        .replace("ď", "d")
    )


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def midpoint(low: float | None, high: float | None) -> float | None:
    if low and high:
        return (low + high) / 2
    return low or high


def room_count(disposition: str | None) -> int | None:
    if not disposition:
        return None
    head = disposition.split("+", 1)[0].strip()
    return int(head) if head.isdigit() else None


def effective_area(property_item: dict[str, Any]) -> float:
    area = float(property_item.get("usable_area_m2") or 0)
    area += float(property_item.get("balcony_area_m2") or 0) * 0.35
    area += float(property_item.get("loggia_area_m2") or 0) * 0.30
    return area


def feature_multiplier(property_item: dict[str, Any]) -> float:
    premium = 1.0
    features = " ".join(property_item.get("outdoor_features", [])).lower()

    if property_item.get("condition") == "excellent" or "skvely stav" in features:
        premium += 0.02

    if property_item.get("estate_type") == "house":
        if float(property_item.get("garden_area_m2") or 0) >= 700:
            premium += 0.04
        if "bazen" in features:
            premium += 0.03
        if "sauna" in features:
            premium += 0.02
        if "krb" in features:
            premium += 0.015
        if int(property_item.get("year_built") or 0) >= 2018:
            premium += 0.03
    else:
        outdoor_area = float(property_item.get("balcony_area_m2") or 0) + float(
            property_item.get("loggia_area_m2") or 0
        )
        if outdoor_area > 0:
            premium += 0.012 + min(outdoor_area / max(float(property_item.get("usable_area_m2") or 1), 1) * 0.05, 0.025)
        if int(property_item.get("floor") or 0) >= 7:
            premium += 0.02
        if "drevena podlaha" in features or "kvalitni kuchyn" in features:
            premium += 0.02

    return premium


def haversine_km(lat1: float | None, lon1: float | None, lat2: float | None, lon2: float | None) -> float | None:
    if None in (lat1, lon1, lat2, lon2):
        return None

    radius_km = 6371.0
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    delta_phi = math.radians(float(lat2) - float(lat1))
    delta_lambda = math.radians(float(lon2) - float(lon1))

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius_km * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def geocode_query(query: str, cache_path: Path = GEOCODE_CACHE_PATH) -> dict[str, Any] | None:
    if not query:
        return None

    cache = load_json(cache_path, {})
    cached = cache.get(query)
    if cached:
        return cached

    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": query, "format": "jsonv2", "limit": 1}
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    with urllib.request.urlopen(request, timeout=25, context=build_ssl_context()) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not payload:
        return None

    first = payload[0]
    result = {
        "lat": float(first["lat"]),
        "lon": float(first["lon"]),
        "display_name": first.get("display_name"),
    }
    cache[query] = result
    save_json(cache_path, cache)
    return result


def fetch_market_pool(
    client: SrealityClient,
    estate_type: str,
    locality_region_id: int,
    max_pages: int,
) -> list[dict[str, Any]]:
    category_main_cb = 1 if estate_type == "flat" else 2
    records: dict[str, dict[str, Any]] = {}

    for page in range(1, max_pages + 1):
        payload = client.fetch_page(
            page=page,
            per_page=60,
            category_type_cb=1,
            category_main_cb=category_main_cb,
            locality_region_id=locality_region_id,
        )
        items = payload.get("_embedded", {}).get("estates", [])
        if not items:
            break

        for item in items:
            parsed = normalize_listing(item, category_type_cb=1, region_id=locality_region_id)
            if (
                not parsed
                or parsed.price_per_m2 is None
                or parsed.usable_area is None
                or parsed.price_czk is None
                or parsed.price_czk <= 1000
                or parsed.price_per_m2 <= 1000
            ):
                continue
            records[parsed.external_id] = {
                "external_id": parsed.external_id,
                "title": parsed.title,
                "locality": parsed.locality,
                "estate_type": parsed.estate_type,
                "disposition": parsed.disposition,
                "usable_area": parsed.usable_area,
                "price_czk": parsed.price_czk,
                "price_per_m2": parsed.price_per_m2,
                "lat": parsed.lat,
                "lon": parsed.lon,
                "url": parsed.url,
                "image_url": parsed.image_url,
            }

        result_size = payload.get("result_size")
        if isinstance(result_size, int) and page * 60 >= result_size:
            break

    return list(records.values())


def locality_overlap(subject_keywords: list[str], locality: str) -> float:
    if not subject_keywords:
        return 0.0
    target = slugify(locality or "")
    hits = 0
    for keyword in subject_keywords:
        if slugify(keyword) in target:
            hits += 1
    return hits / len(subject_keywords)


def candidate_window(subject_area: float, estate_type: str) -> tuple[float, float]:
    if estate_type == "house":
        return subject_area * 0.50, subject_area * 2.10
    return subject_area * 0.55, subject_area * 1.85


def select_comparables(property_item: dict[str, Any], candidates: list[dict[str, Any]], geocode: dict[str, Any] | None) -> list[dict[str, Any]]:
    subject_area = float(property_item.get("usable_area_m2") or 0)
    subject_rooms = room_count(property_item.get("disposition"))
    keywords = property_item.get("market", {}).get("locality_keywords", [])
    min_area, max_area = candidate_window(subject_area, property_item["estate_type"])
    scored: list[dict[str, Any]] = []

    for candidate in candidates:
        area = float(candidate.get("usable_area") or 0)
        if area < min_area or area > max_area:
            continue

        distance = haversine_km(
            geocode.get("lat") if geocode else None,
            geocode.get("lon") if geocode else None,
            candidate.get("lat"),
            candidate.get("lon"),
        )
        location_similarity = 0.35
        if distance is not None:
            radius = 22 if property_item["estate_type"] == "house" else 11
            location_similarity = max(0.0, 1 - min(distance / radius, 1.2))

        locality_similarity = locality_overlap(keywords, str(candidate.get("locality") or ""))
        size_similarity = max(0.0, 1 - abs(area - subject_area) / max(subject_area, 1))

        candidate_rooms = room_count(candidate.get("disposition"))
        if subject_rooms is None or candidate_rooms is None:
            disposition_similarity = 0.55
        elif subject_rooms == candidate_rooms:
            disposition_similarity = 1.0
        elif abs(subject_rooms - candidate_rooms) == 1:
            disposition_similarity = 0.72
        else:
            disposition_similarity = 0.42

        score = (
            0.42 * size_similarity
            + 0.24 * location_similarity
            + 0.18 * disposition_similarity
            + 0.16 * locality_similarity
        )
        if score < 0.32:
            continue

        scored.append(
            {
                **candidate,
                "distance_km": distance,
                "size_similarity": round(size_similarity, 4),
                "location_similarity": round(location_similarity, 4),
                "disposition_similarity": round(disposition_similarity, 4),
                "locality_similarity": round(locality_similarity, 4),
                "score": round(score, 4),
            }
        )

    scored.sort(key=lambda item: (item["score"], item["locality_similarity"], -abs(item["usable_area"] - subject_area)), reverse=True)
    return scored[:12]


def estimate_property_value(
    property_item: dict[str, Any],
    comparables: list[dict[str, Any]],
) -> dict[str, Any]:
    manual_low = property_item.get("manual_estimate_low_czk")
    manual_high = property_item.get("manual_estimate_high_czk")
    manual_mid = midpoint(manual_low, manual_high)
    purchase_price = property_item.get("purchase_price_czk")
    subject_effective_area = effective_area(property_item)
    premium = feature_multiplier(property_item)

    if not comparables:
        estimate = float(manual_mid or purchase_price or 0)
        margin = 0.12 if manual_mid else 0.18
        return {
            "estimated_value_czk": round(estimate),
            "estimate_low_czk": round(estimate * (1 - margin)),
            "estimate_high_czk": round(estimate * (1 + margin)),
            "weighted_price_per_m2_czk": None,
            "median_price_per_m2_czk": None,
            "confidence_score": 0.28 if manual_mid else 0.18,
            "comparable_count": 0,
            "methodology": "Fallback to the manual anchor because there were not enough live comparables.",
        }

    ppm2_values = [float(item["price_per_m2"]) for item in comparables]
    weights = [max(item["score"], 0.05) ** 2 for item in comparables]
    weighted_ppm2 = sum(value * weight for value, weight in zip(ppm2_values, weights)) / sum(weights)
    median_ppm2 = statistics.median(ppm2_values)
    market_ppm2 = 0.65 * weighted_ppm2 + 0.35 * median_ppm2
    market_value = market_ppm2 * subject_effective_area * premium

    avg_location = sum(item["location_similarity"] for item in comparables) / len(comparables)
    avg_size = sum(item["size_similarity"] for item in comparables) / len(comparables)
    avg_disp = sum(item["disposition_similarity"] for item in comparables) / len(comparables)
    confidence = clamp(
        0.22
        + 0.32 * min(len(comparables) / 8, 1)
        + 0.20 * avg_location
        + 0.17 * avg_size
        + 0.09 * avg_disp,
        0.18,
        0.94,
    )

    manual_weight = 0.0
    if manual_mid:
        manual_weight = clamp(0.44 - confidence * 0.34, 0.10, 0.30)

    estimate = market_value * (1 - manual_weight) + float(manual_mid or 0) * manual_weight
    margin = clamp(0.19 - confidence * 0.11, 0.07, 0.18)
    low = estimate * (1 - margin)
    high = estimate * (1 + margin)

    if manual_low and manual_high:
        low = low * (1 - manual_weight) + float(manual_low) * manual_weight
        high = high * (1 - manual_weight) + float(manual_high) * manual_weight

    return {
        "estimated_value_czk": round(estimate),
        "estimate_low_czk": round(low),
        "estimate_high_czk": round(high),
        "weighted_price_per_m2_czk": round(weighted_ppm2),
        "median_price_per_m2_czk": round(median_ppm2),
        "confidence_score": round(confidence, 2),
        "comparable_count": len(comparables),
        "methodology": "Weighted Prague Sreality comparables blended with your manual anchor when confidence is lower.",
    }


def property_missing_inputs(property_item: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not property_item.get("purchase_price_czk"):
        missing.append("purchase price")
    if property_item.get("use") == "unknown":
        missing.append("usage (rental vs owner occupied)")
    missing.extend(
        [
            "monthly mortgage payment",
            "interest rate",
            "monthly operating costs",
            "annual insurance",
            "annual property tax",
        ]
    )
    return missing


def build_history(snapshot: dict[str, Any], previous_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    history = list(previous_snapshot.get("history", []))
    entry = {
        "date": snapshot["generated_at"][:10],
        "estimated_value_czk": snapshot["totals"]["estimated_value_czk"],
        "mortgage_balance_czk": snapshot["totals"]["mortgage_balance_czk"],
        "real_estate_equity_czk": snapshot["totals"]["real_estate_equity_czk"],
    }
    history = [item for item in history if item.get("date") != entry["date"]]
    history.append(entry)
    history.sort(key=lambda item: item.get("date", ""))
    return history[-120:]


def build_narrative(snapshot: dict[str, Any], previous_snapshot: dict[str, Any]) -> dict[str, Any]:
    properties = snapshot["properties"]
    previous_lookup = {item["id"]: item for item in previous_snapshot.get("properties", [])}
    most_conviction = max(properties, key=lambda item: item["valuation"]["confidence_score"])
    narrative_lines = [
        f"Today the portfolio is marked at {snapshot['totals']['estimated_value_czk']:,} CZK before cash and other debts.".replace(",", " "),
        f"The strongest live valuation confidence sits on {most_conviction['name']} at {int(most_conviction['valuation']['confidence_score'] * 100)}%.",
    ]

    if previous_snapshot.get("totals"):
        delta = snapshot["totals"]["estimated_value_czk"] - previous_snapshot["totals"].get("estimated_value_czk", 0)
        direction = "up" if delta >= 0 else "down"
        narrative_lines.append(
            f"Versus the last stored snapshot, portfolio market value is {direction} by {abs(delta):,} CZK.".replace(",", " ")
        )

    movers: list[tuple[float, str]] = []
    for property_item in properties:
        previous_value = previous_lookup.get(property_item["id"], {}).get("valuation", {}).get("estimated_value_czk")
        current_value = property_item["valuation"]["estimated_value_czk"]
        if previous_value:
            movers.append((current_value - previous_value, property_item["name"]))

    movers.sort(key=lambda item: abs(item[0]), reverse=True)
    if movers:
        change, name = movers[0]
        narrative_lines.append(
            f"Biggest move: {name} {'+' if change >= 0 else '-'}{abs(change):,} CZK since the previous refresh.".replace(",", " ")
        )

    pending_inputs = sum(len(item["missing_inputs"]) for item in properties)
    narrative_lines.append(f"There are still {pending_inputs} financial inputs waiting to be filled in the app for sharper cashflow math.")

    return {
        "headline": "Daily pulse for your residential balance sheet",
        "lines": narrative_lines,
    }


def build_snapshot_payload(
    seed_path: Path = SEED_PATH,
    output_path: Path = OUTPUT_PATH,
    geocode_cache_path: Path = GEOCODE_CACHE_PATH,
) -> dict[str, Any]:
    seed = load_json(seed_path, {})
    previous_snapshot = load_json(output_path, {})
    client = SrealityClient(timeout_seconds=25)
    pool_cache: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
    properties_output: list[dict[str, Any]] = []

    for property_item in seed.get("properties", []):
        market = property_item.get("market", {})
        region_id = int(market.get("locality_region_id", 10))
        max_pages = int(market.get("max_pages", 12))
        pool_key = (property_item["estate_type"], region_id, max_pages)
        if pool_key not in pool_cache:
            pool_cache[pool_key] = fetch_market_pool(client, property_item["estate_type"], region_id, max_pages)

        geocode = geocode_query(property_item.get("address", ""), cache_path=geocode_cache_path)
        comparables = select_comparables(property_item, pool_cache[pool_key], geocode)
        valuation = estimate_property_value(property_item, comparables)
        mortgage_balance = int(property_item.get("mortgage_balance_czk") or 0)
        estimated_value = int(valuation["estimated_value_czk"])
        previous_lookup = {
            item["id"]: item for item in previous_snapshot.get("properties", [])
        }
        previous_value = previous_lookup.get(property_item["id"], {}).get("valuation", {}).get("estimated_value_czk")

        properties_output.append(
            {
                "id": property_item["id"],
                "label": property_item["label"],
                "name": property_item["name"],
                "address": property_item.get("address"),
                "locality": property_item.get("locality"),
                "estate_type": property_item["estate_type"],
                "disposition": property_item.get("disposition"),
                "use": property_item.get("use", "unknown"),
                "usable_area_m2": property_item.get("usable_area_m2"),
                "balcony_area_m2": property_item.get("balcony_area_m2"),
                "loggia_area_m2": property_item.get("loggia_area_m2"),
                "garden_area_m2": property_item.get("garden_area_m2"),
                "floor": property_item.get("floor"),
                "year_built": property_item.get("year_built"),
                "year_purchased": property_item.get("year_purchased"),
                "outdoor_features": property_item.get("outdoor_features", []),
                "view_note": property_item.get("view_note"),
                "manual_estimate_low_czk": property_item.get("manual_estimate_low_czk"),
                "manual_estimate_high_czk": property_item.get("manual_estimate_high_czk"),
                "finance": {
                    "purchase_price_czk": property_item.get("purchase_price_czk"),
                    "mortgage_balance_czk": mortgage_balance,
                    "equity_czk": estimated_value - mortgage_balance,
                    "ltv_pct": round((mortgage_balance / estimated_value) * 100, 1) if estimated_value else None,
                },
                "valuation": {
                    **valuation,
                    "value_change_vs_purchase_czk": (
                        estimated_value - int(property_item["purchase_price_czk"])
                        if property_item.get("purchase_price_czk")
                        else None
                    ),
                    "value_change_vs_previous_czk": (
                        estimated_value - int(previous_value) if previous_value else None
                    ),
                },
                "geocode": geocode,
                "comparables": [
                    {
                        "title": item["title"],
                        "locality": item["locality"],
                        "price_czk": round(item["price_czk"]),
                        "price_per_m2_czk": round(item["price_per_m2"]),
                        "usable_area_m2": round(item["usable_area"], 1),
                        "distance_km": round(item["distance_km"], 1) if item["distance_km"] is not None else None,
                        "url": item["url"],
                        "image_url": item["image_url"],
                        "score": item["score"],
                    }
                    for item in comparables[:5]
                ],
                "missing_inputs": property_missing_inputs(property_item),
            }
        )

    totals = defaultdict(int)
    for property_item in properties_output:
        totals["estimated_value_czk"] += int(property_item["valuation"]["estimated_value_czk"])
        totals["mortgage_balance_czk"] += int(property_item["finance"]["mortgage_balance_czk"])

    snapshot = {
        "generated_at": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "portfolio_name": seed.get("portfolio_name", "Portfolio"),
        "currency": seed.get("currency", "CZK"),
        "timezone": seed.get("timezone", "Europe/Prague"),
        "recommended_refresh_time": seed.get("recommended_refresh_time", "08:15"),
        "cash_czk": int(seed.get("cash_czk") or 0),
        "pension_czk": int(seed.get("pension_czk") or 0),
        "properties": properties_output,
        "totals": {
            "estimated_value_czk": totals["estimated_value_czk"],
            "mortgage_balance_czk": totals["mortgage_balance_czk"],
            "real_estate_equity_czk": totals["estimated_value_czk"] - totals["mortgage_balance_czk"],
        },
    }
    snapshot["history"] = build_history(snapshot, previous_snapshot)
    snapshot["narrative"] = build_narrative(snapshot, previous_snapshot)
    return snapshot


def main() -> None:
    payload = build_snapshot_payload()
    save_json(OUTPUT_PATH, payload)
    save_snapshot_js(OUTPUT_JS_PATH, payload)
    print(
        f"Wrote {len(payload['properties'])} properties to {OUTPUT_PATH} at {payload['generated_at']}"
    )


if __name__ == "__main__":
    main()
