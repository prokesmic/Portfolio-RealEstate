from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ListingRecord:
    external_id: str
    region_id: int | None
    area_group: str | None
    url: str
    title: str
    locality: str
    locality_slug: str
    category_type: str
    estate_type: str
    property_kind: str
    disposition: str
    usable_area: float | None
    land_area: float | None
    price_czk: int
    currency: str
    price_per_m2: float | None
    lat: float | None
    lon: float | None
    image_url: str | None
    image_count: int | None
    has_floor_plan: bool
    has_video: bool
    labels: list[str]
    is_new_listing: bool
    source_payload: str


class ListingSource(Protocol):
    def fetch_records(self) -> list[ListingRecord]:
        ...
