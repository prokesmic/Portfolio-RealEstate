from __future__ import annotations

import unittest

from backend.sreality_client import (
    build_detail_url,
    normalize_disposition_for_url,
    normalize_listing,
)


class SrealityClientParsingTests(unittest.TestCase):
    def test_normalize_disposition_for_url(self) -> None:
        self.assertEqual(normalize_disposition_for_url("3+kt"), "3+kk")
        self.assertEqual(normalize_disposition_for_url(" 2+1 "), "2+1")
        self.assertIsNone(normalize_disposition_for_url("unknown"))

    def test_build_detail_url(self) -> None:
        item = {
            "hash_id": 4217447244,
            "seo": {"locality": "bedrichov-bedrichov-"},
        }
        url = build_detail_url(
            item=item,
            category_type="sale",
            estate_type="flat",
            disposition="3+kt",
        )
        self.assertEqual(
            url,
            "https://www.sreality.cz/detail/prodej/byt/3+kk/bedrichov-bedrichov-/4217447244",
        )

    def test_normalize_listing_prefers_detail_url(self) -> None:
        item = {
            "hash_id": 4217447244,
            "name": "For sale apartment 3+kt 121 m2",
            "locality": "Bedrichov",
            "price": 12000000,
            "category": 1,
            "category_type_cb": 1,
            "labelsAll": ["3+kt", "121 m²"],
            "seo": {
                "category_main_cb": 1,
                "category_type_cb": 1,
                "locality": "bedrichov-bedrichov-",
            },
            "_links": {"self": {"href": "/en/v2/estates/4217447244"}},
        }
        listing = normalize_listing(item)
        self.assertIsNotNone(listing)
        assert listing is not None
        self.assertIn("/detail/prodej/byt/3+kk/bedrichov-bedrichov-/4217447244", listing.url)


if __name__ == "__main__":
    unittest.main()
