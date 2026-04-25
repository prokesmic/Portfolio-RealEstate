from __future__ import annotations

import json
import unittest
from pathlib import Path

from backend.sreality_source import SrealitySource


class FakeClient:
    def __init__(self, fixture_items: list[dict]):
        self.fixture_items = fixture_items

    def fetch_page(
        self,
        page: int = 1,
        per_page: int = 60,
        category_type_cb: int | None = None,
        category_main_cb: int | None = None,
        locality_region_id: int | None = None,
    ) -> dict:
        if page > 1:
            return {"_embedded": {"estates": []}}

        data = self.fixture_items
        if category_type_cb is not None:
            data = [item for item in data if item.get("category_type_cb") == category_type_cb]
        if category_main_cb is not None:
            data = [item for item in data if item.get("category_main_cb") == category_main_cb]
        return {"_embedded": {"estates": data}}


class SrealitySourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fixture_path = Path(__file__).resolve().parent.parent / "sample_data" / "sreality_sample.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        cls.fixture_items = payload["_embedded"]["estates"]

    def test_fetch_records_normalizes_sales_inventory(self) -> None:
        source = SrealitySource(
            client=FakeClient(self.fixture_items),
            sync_pages=2,
            max_price_czk=50_000_000,
            region_ids=[10],
            estate_type_cbs=[1, 2, 3],
        )

        records = source.fetch_records()

        self.assertEqual(len(records), 9)
        self.assertTrue(all(record.category_type == "sale" for record in records))
        self.assertTrue(all(record.currency == "CZK" for record in records))


if __name__ == "__main__":
    unittest.main()
