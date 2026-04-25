from __future__ import annotations

from .listing_source import ListingRecord
from .sreality_client import SrealityClient, normalize_listing


class SrealitySource:
    def __init__(
        self,
        client: SrealityClient,
        sync_pages: int,
        max_price_czk: int,
        region_ids: list[int],
        estate_type_cbs: list[int],
    ) -> None:
        self.client = client
        self.sync_pages = sync_pages
        self.max_price_czk = max_price_czk
        self.region_ids = region_ids
        self.estate_type_cbs = estate_type_cbs

    def fetch_records(self) -> list[ListingRecord]:
        records: list[ListingRecord] = []
        seen: set[str] = set()

        for region_id in self.region_ids:
            for estate_cb in self.estate_type_cbs:
                for page in range(1, self.sync_pages + 1):
                    payload = self.client.fetch_page(
                        page=page,
                        per_page=60,
                        category_type_cb=1,
                        category_main_cb=estate_cb,
                        locality_region_id=region_id,
                    )
                    items = payload.get("_embedded", {}).get("estates", [])
                    if not items:
                        break

                    parsed_any = False
                    for item in items:
                        parsed = normalize_listing(
                            item,
                            category_type_cb=1,
                            region_id=region_id,
                        )
                        if not parsed:
                            continue
                        if parsed.external_id in seen:
                            continue
                        if parsed.price_czk > self.max_price_czk:
                            continue
                        if parsed.category_type != "sale":
                            continue
                        if parsed.estate_type not in {"flat", "house", "land"}:
                            continue

                        seen.add(parsed.external_id)
                        records.append(parsed)
                        parsed_any = True

                    if not parsed_any:
                        break

                    result_size = payload.get("result_size")
                    if isinstance(result_size, int) and page * 60 >= result_size:
                        break

        return records
