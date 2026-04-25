from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.database import Database
from backend.service import DealsService


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
    ):
        if page > 1:
            return {"_embedded": {"estates": []}}

        data = self.fixture_items
        if category_type_cb is not None:
            data = [item for item in data if item.get("category_type_cb") == category_type_cb]
        if category_main_cb is not None:
            data = [item for item in data if item.get("category_main_cb") == category_main_cb]
        return {"_embedded": {"estates": data}}


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fixture_path = Path(__file__).resolve().parent.parent / "sample_data" / "sreality_sample.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        cls.fixture_items = payload["_embedded"]["estates"]

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = str(Path(self.temp_dir.name) / "test.db")
        self.db = Database(db_path)
        self.service = DealsService(db=self.db, client=FakeClient(self.fixture_items))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_sync_and_stats(self) -> None:
        result = self.service.run_sync(max_pages=3)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["stored_count"], 12)

        stats = self.service.stats()
        self.assertEqual(stats["total_listings"], 12)
        self.assertIn("Fair", stats["by_bucket"])

    def test_filtering(self) -> None:
        self.service.run_sync(max_pages=2)

        all_items = self.service.list_listings({"limit": "100"})
        self.assertEqual(all_items["total"], 12)

        prague = self.service.list_listings({"locality": "Praha 3 - Žižkov", "limit": "100"})
        self.assertEqual(prague["total"], 3)

        high = self.service.list_listings({"deal_bucket": "High", "limit": "100"})
        self.assertGreaterEqual(high["total"], 1)

    def test_watchlist(self) -> None:
        self.service.run_sync(max_pages=2)
        self.service.save_watchlist("1001", note="Strong contender")

        watch = self.service.list_watchlist()
        self.assertEqual(len(watch), 1)
        self.assertEqual(watch[0]["external_id"], "1001")

        saved_only = self.service.list_listings({"saved_only": "1", "limit": "50"})
        self.assertEqual(saved_only["total"], 1)

        self.service.remove_watchlist("1001")
        self.assertEqual(len(self.service.list_watchlist()), 0)


if __name__ == "__main__":
    unittest.main()
