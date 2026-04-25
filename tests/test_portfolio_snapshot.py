from __future__ import annotations

import unittest

from scripts.build_portfolio_snapshot import estimate_property_value, feature_multiplier, select_comparables


class PortfolioSnapshotTests(unittest.TestCase):
    def test_feature_multiplier_rewards_quality_features(self) -> None:
        property_item = {
            "estate_type": "house",
            "garden_area_m2": 900,
            "year_built": 2020,
            "outdoor_features": ["Bazen", "Venkovni sauna", "Krb", "Skvely stav"],
        }

        self.assertGreater(feature_multiplier(property_item), 1.10)

    def test_select_comparables_prefers_local_matches(self) -> None:
        property_item = {
            "estate_type": "flat",
            "usable_area_m2": 45,
            "disposition": "2+kk",
            "market": {"locality_keywords": ["strizkov", "praha 9"]},
        }
        geocode = {"lat": 50.125, "lon": 14.485}
        candidates = [
            {
                "title": "Nearby match",
                "locality": "Praha 9 - Strizkov",
                "disposition": "2+kk",
                "usable_area": 43,
                "price_per_m2": 160000,
                "price_czk": 6880000,
                "lat": 50.126,
                "lon": 14.486,
                "url": "https://example.com/near",
                "image_url": None,
            },
            {
                "title": "Far mismatch",
                "locality": "Praha 5 - Smichov",
                "disposition": "4+kk",
                "usable_area": 44,
                "price_per_m2": 150000,
                "price_czk": 6600000,
                "lat": 50.075,
                "lon": 14.404,
                "url": "https://example.com/far",
                "image_url": None,
            },
        ]

        comparables = select_comparables(property_item, candidates, geocode)

        self.assertEqual(comparables[0]["title"], "Nearby match")

    def test_estimate_blends_manual_anchor_with_market(self) -> None:
        property_item = {
            "usable_area_m2": 41,
            "estate_type": "flat",
            "manual_estimate_low_czk": 6800000,
            "manual_estimate_high_czk": 7000000,
        }
        comparables = [
            {
                "price_per_m2": 165000,
                "score": 0.92,
                "location_similarity": 0.91,
                "size_similarity": 0.95,
                "disposition_similarity": 1.0,
            },
            {
                "price_per_m2": 162000,
                "score": 0.88,
                "location_similarity": 0.84,
                "size_similarity": 0.90,
                "disposition_similarity": 0.9,
            },
        ]

        valuation = estimate_property_value(property_item, comparables)

        self.assertGreater(valuation["estimated_value_czk"], 6500000)
        self.assertLess(valuation["estimated_value_czk"], 7300000)
        self.assertGreater(valuation["confidence_score"], 0.5)


if __name__ == "__main__":
    unittest.main()
