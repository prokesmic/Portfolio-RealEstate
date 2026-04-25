from __future__ import annotations

import json
import re
import ssl
import urllib.parse
import urllib.request
from typing import Any

from .listing_source import ListingRecord
from .scoring import slugify_locality

API_URL = "https://www.sreality.cz/api/en/v2/estates"


class SrealityClient:
    def __init__(self, timeout_seconds: int = 25):
        self.timeout_seconds = timeout_seconds
        self._ssl_context = self._build_ssl_context()

    @staticmethod
    def _build_ssl_context() -> ssl.SSLContext:
        try:
            import certifi

            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            return ssl.create_default_context()

    def fetch_page(
        self,
        page: int = 1,
        per_page: int = 60,
        category_type_cb: int | None = None,
        category_main_cb: int | None = None,
        locality_region_id: int | None = None,
    ) -> dict[str, Any]:
        query: dict[str, str] = {"page": str(page), "per_page": str(per_page)}
        if category_type_cb is not None:
            query["category_type_cb"] = str(category_type_cb)
        if category_main_cb is not None:
            query["category_main_cb"] = str(category_main_cb)
        if locality_region_id is not None:
            query["locality_region_id"] = str(locality_region_id)

        url = f"{API_URL}?{urllib.parse.urlencode(query)}"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(
            request,
            timeout=self.timeout_seconds,
            context=self._ssl_context,
        ) as response:
            return json.loads(response.read().decode("utf-8"))


def parse_price(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)

    digits = re.sub(r"[^0-9]", "", str(value))
    if not digits:
        return None
    return int(digits)


def parse_area(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).replace(",", ".")
    match = re.search(r"(\d+(?:\.\d+)?)\s*m", text)
    if not match:
        return None
    return float(match.group(1))


def infer_disposition(item: dict[str, Any]) -> str:
    for candidate in [
        item.get("disposition"),
        item.get("name"),
        *item.get("labelsAll", []),
        *item.get("labels", []),
    ]:
        if not candidate:
            continue
        text = str(candidate)
        found = re.search(r"\b\d\+[^\s,]+", text)
        if found:
            return found.group(0)
    return "unknown"


def infer_area(item: dict[str, Any]) -> float | None:
    values = [item.get("usable_area"), item.get("area"), item.get("name")]
    values.extend(item.get("labelsAll", []))
    for value in values:
        parsed = parse_area(value)
        if parsed:
            return parsed
    return None


def infer_estate_type(item: dict[str, Any]) -> str:
    main_cb_map = {
        1: "flat",
        2: "house",
        3: "land",
        4: "commercial",
        5: "other",
        6: "project",
        7: "garage",
        8: "facility",
    }

    raw_main = item.get("category_main_cb")
    if isinstance(raw_main, int) and raw_main in main_cb_map:
        return main_cb_map[raw_main]

    category = item.get("category")
    if isinstance(category, int) and category in main_cb_map:
        return main_cb_map[category]

    seo = item.get("seo") or {}
    if isinstance(seo, dict):
        seo_main = seo.get("category_main_cb")
        if isinstance(seo_main, int) and seo_main in main_cb_map:
            return main_cb_map[seo_main]

        text = " ".join(str(v) for v in seo.values())
        for token in ["byt", "dum", "pozemek", "komercni", "garaz"]:
            if token in text.lower():
                mapping = {
                    "byt": "flat",
                    "dum": "house",
                    "pozemek": "land",
                    "komercni": "commercial",
                    "garaz": "garage",
                }
                return mapping[token]

    return "unknown"


def infer_category_type(item: dict[str, Any], category_type_cb: int | None = None) -> str:
    if category_type_cb == 1:
        return "sale"
    if category_type_cb == 2:
        return "rent"

    raw = item.get("category_type_cb")
    if raw == 1:
        return "sale"
    if raw == 2:
        return "rent"

    lower_name = str(item.get("name", "")).lower()
    if "pronajem" in lower_name:
        return "rent"
    if "prodej" in lower_name:
        return "sale"
    return "unknown"


def pick_image(item: dict[str, Any]) -> str | None:
    links = item.get("_links")
    if not isinstance(links, dict):
        return None

    images = links.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            href = first.get("href")
            if href:
                return str(href).replace("{index}", "0")

    image = links.get("image")
    if isinstance(image, dict):
        href = image.get("href")
        if href:
            return str(href)

    return None


def extract_image_count(item: dict[str, Any]) -> int | None:
    raw = item.get("advert_images_count")
    if isinstance(raw, int):
        return raw
    links = item.get("_links")
    if isinstance(links, dict):
        images = links.get("images")
        if isinstance(images, list):
            return len(images)
    return None


def pick_url(item: dict[str, Any]) -> str:
    links = item.get("_links") or {}
    if isinstance(links, dict):
        link_self = links.get("self")
        if isinstance(link_self, dict):
            href = str(link_self.get("href", "")).strip()
            if href.startswith("http"):
                return href
            if href.startswith("/detail/"):
                return f"https://www.sreality.cz{href}"

    return ""


def normalize_disposition_for_url(disposition: str) -> str | None:
    raw = (disposition or "").strip().lower()
    if not raw or raw == "unknown":
        return None
    cleaned = re.sub(r"\s+", "", raw)
    cleaned = cleaned.replace("kt", "kk")
    if re.fullmatch(r"\d\+[a-z0-9]+", cleaned):
        return cleaned
    return None


def build_detail_url(
    item: dict[str, Any],
    category_type: str,
    estate_type: str,
    disposition: str,
) -> str | None:
    seo = item.get("seo") or {}
    locality_slug = ""
    if isinstance(seo, dict):
        locality_slug = str(seo.get("locality") or "").strip()

    external_id = str(item.get("hash_id") or item.get("id") or "").strip()
    if not locality_slug or not external_id:
        return None

    type_slug_map = {"sale": "prodej", "rent": "pronajem"}
    estate_slug_map = {
        "flat": "byt",
        "house": "dum",
        "land": "pozemek",
        "commercial": "komercni",
        "garage": "garaz",
    }

    type_slug = type_slug_map.get(category_type)
    estate_slug = estate_slug_map.get(estate_type)
    if not type_slug or not estate_slug:
        return None

    disposition_slug = normalize_disposition_for_url(disposition)
    if disposition_slug:
        return (
            f"https://www.sreality.cz/detail/{type_slug}/{estate_slug}/"
            f"{disposition_slug}/{locality_slug}/{external_id}"
        )
    return f"https://www.sreality.cz/detail/{type_slug}/{estate_slug}/{locality_slug}/{external_id}"


def pick_fallback_url(item: dict[str, Any]) -> str:
    links = item.get("_links") or {}
    if isinstance(links, dict):
        link_self = links.get("self")
        if isinstance(link_self, dict):
            href = str(link_self.get("href", "")).strip()
            if href.startswith("http"):
                return href
            if href.startswith("/"):
                return f"https://www.sreality.cz{href}"

    hash_id = item.get("hash_id") or item.get("id") or ""
    return f"https://www.sreality.cz/detail/{hash_id}"


def pick_coordinates(item: dict[str, Any]) -> tuple[float | None, float | None]:
    gps = item.get("gps")
    if isinstance(gps, dict):
        lat = gps.get("lat")
        lon = gps.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return float(lat), float(lon)

    return None, None


def extract_labels(item: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for source in [item.get("labels"), item.get("labelsAll")]:
        if isinstance(source, list):
            for entry in source:
                if isinstance(entry, list):
                    for label in entry:
                        if isinstance(label, str) and label.strip():
                            labels.append(label.strip())
                elif isinstance(entry, str) and entry.strip():
                    labels.append(entry.strip())
    return sorted(set(labels))


def infer_property_kind(estate_type: str, item: dict[str, Any]) -> str:
    if estate_type == "flat":
        return "apartment"
    if estate_type == "land":
        return "land"

    name = str(item.get("name") or "").lower()
    locality = str(item.get("locality") or "").lower()
    merged = f"{name} {locality}"
    if "chata" in merged or "chat" in merged:
        return "cottage"
    if "chalupa" in merged or "chalup" in merged:
        return "chalet"
    return "house"


def normalize_listing(
    item: dict[str, Any],
    category_type_cb: int | None = None,
    region_id: int | None = None,
) -> ListingRecord | None:
    external_id_raw = item.get("hash_id") or item.get("id")
    if not external_id_raw:
        return None

    price = parse_price(item.get("price"))
    if not price:
        return None

    locality = str(item.get("locality") or "Unknown").strip()
    usable_area = infer_area(item)
    land_area = usable_area if infer_estate_type(item) == "land" else None
    area_for_ppm2 = land_area or usable_area
    price_per_m2 = (price / area_for_ppm2) if area_for_ppm2 and area_for_ppm2 > 0 else None

    lat, lon = pick_coordinates(item)

    category_type = infer_category_type(item, category_type_cb=category_type_cb)
    estate_type = infer_estate_type(item)
    property_kind = infer_property_kind(estate_type, item)
    disposition = infer_disposition(item)

    detail_url = build_detail_url(
        item=item,
        category_type=category_type,
        estate_type=estate_type,
        disposition=disposition,
    )

    direct_url = pick_url(item)

    return ListingRecord(
        external_id=str(external_id_raw),
        region_id=region_id,
        area_group=None,
        url=detail_url or direct_url or pick_fallback_url(item),
        title=str(item.get("name") or "Untitled listing").strip(),
        locality=locality,
        locality_slug=slugify_locality(locality),
        category_type=category_type,
        estate_type=estate_type,
        property_kind=property_kind,
        disposition=disposition,
        usable_area=usable_area,
        land_area=land_area,
        price_czk=price,
        currency="CZK",
        price_per_m2=price_per_m2,
        lat=lat,
        lon=lon,
        image_url=pick_image(item),
        image_count=extract_image_count(item),
        has_floor_plan=bool(item.get("has_floor_plan")),
        has_video=bool(item.get("has_video") or item.get("has_matterport_url")),
        labels=extract_labels(item),
        is_new_listing=bool(item.get("new")),
        source_payload=json.dumps(item, ensure_ascii=False),
    )
