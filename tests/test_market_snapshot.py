from __future__ import annotations

import unittest

from scripts.build_market_snapshot import (
    AgencyListing,
    deduplicate_listings,
    parse_realestate_lefkada_detail_html,
    parse_sitemap_urls,
)


class MarketSnapshotTests(unittest.TestCase):
    def make_listing(self, **overrides) -> AgencyListing:
        base = AgencyListing(
            external_id="a",
            source_name="Source A",
            area_group="crete",
            estate_type="house",
            property_kind="House",
            title="Stone house with sea view in Vamos",
            locality="Vamos",
            url="https://example.com/a",
            image_url="https://example.com/a.jpg",
            usable_area=120.0,
            land_area=500.0,
            price_eur=350000,
            currency="EUR",
            price_per_m2=2916.67,
            bedrooms=3,
            bathrooms=2,
            lat=35.4,
            lon=24.2,
            image_count=6,
            first_seen="2026-04-01T00:00:00Z",
            last_seen="2026-04-06T00:00:00Z",
            price_drop_pct=0.0,
            quality_reasons=[],
        )
        for key, value in overrides.items():
            setattr(base, key, value)
        return base

    def test_deduplicate_listings_removes_cross_source_duplicates(self) -> None:
        richer = self.make_listing(
            external_id="source-a-1",
            source_name="Source A",
            image_count=8,
            image_url="https://example.com/a-1.jpg",
        )
        duplicate = self.make_listing(
            external_id="source-b-99",
            source_name="Source B",
            url="https://example.com/b-99",
            image_count=1,
            image_url=None,
        )
        distinct = self.make_listing(
            external_id="source-c-5",
            source_name="Source C",
            title="Village house in Spili",
            locality="Spili",
            price_eur=180000,
            usable_area=95.0,
            land_area=150.0,
            lat=35.28,
            lon=24.53,
        )

        kept = deduplicate_listings([duplicate, richer, distinct])

        self.assertEqual(len(kept), 2)
        self.assertEqual({item.external_id for item in kept}, {"source-a-1", "source-c-5"})

    def test_parse_sitemap_urls_extracts_locations(self) -> None:
        xml = """
        <urlset>
          <url><loc>https://example.com/property/</loc></url>
          <url><loc>https://example.com/property/villa-in-sivota/</loc></url>
          <url><loc>https://example.com/property/apartment-in-nydri/</loc></url>
        </urlset>
        """
        self.assertEqual(
            parse_sitemap_urls(xml),
            [
                "https://example.com/property/",
                "https://example.com/property/villa-in-sivota/",
                "https://example.com/property/apartment-in-nydri/",
            ],
        )

    def test_parse_realestate_lefkada_detail_html_parses_residential_listing(self) -> None:
        html = """
        <html>
          <head>
            <meta property="og:title" content="Villa in Sivota" />
            <meta property="og:description" content="Villa in Sivota 280 m2 with plot 4.500 m2 with beautiful sea view. Villa has 5 rooms and 5 bathrooms." />
            <meta property="og:image" content="https://example.com/villa.jpg" />
          </head>
          <body>
            <script>
              var listingMap = {"lat":"38.6241","lng":"20.7214","price":"1300000"};
            </script>
            <div class="price">€ 1.300.000</div>
          </body>
        </html>
        """

        listing = parse_realestate_lefkada_detail_html(
            "https://www.realestate-lefkada.com/property/villa-in-sivota/",
            html,
            {},
            "2026-04-06T00:00:00Z",
        )

        self.assertIsNotNone(listing)
        assert listing is not None
        self.assertEqual(listing.source_name, "Real Estate Lefkada")
        self.assertEqual(listing.area_group, "lefkada")
        self.assertEqual(listing.estate_type, "house")
        self.assertEqual(listing.property_kind, "Villa")
        self.assertEqual(listing.price_eur, 1_300_000)
        self.assertEqual(listing.usable_area, 280.0)
        self.assertEqual(listing.land_area, 4500.0)
        self.assertEqual(listing.bedrooms, 5)
        self.assertEqual(listing.bathrooms, 5)
        self.assertEqual(listing.lat, 38.6241)
        self.assertEqual(listing.lon, 20.7214)


if __name__ == "__main__":
    unittest.main()
