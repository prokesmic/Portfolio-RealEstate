import unittest

from backend.scoring import area_bucket, build_segment_key, deal_from_median, slugify_locality


class ScoringTests(unittest.TestCase):
    def test_slugify_locality(self) -> None:
        self.assertEqual(slugify_locality("Praha 3 - Žižkov"), "praha-3-zizkov")

    def test_area_bucket(self) -> None:
        self.assertEqual(area_bucket(None), "unknown")
        self.assertEqual(area_bucket(31), "tiny")
        self.assertEqual(area_bucket(45), "compact")
        self.assertEqual(area_bucket(76), "standard")
        self.assertEqual(area_bucket(101), "large")
        self.assertEqual(area_bucket(160), "xlarge")

    def test_build_segment_key(self) -> None:
        key = build_segment_key("sale", "flat", "praha", "2+kk", 52)
        self.assertEqual(key, "sale|flat|praha|2+kk|compact")

    def test_deal_from_median(self) -> None:
        score, bucket = deal_from_median(100000, 140000)
        self.assertGreater(score, 0)
        self.assertEqual(bucket, "Jackpot")

        score, bucket = deal_from_median(125000, 130000)
        self.assertEqual(bucket, "Fair")

        score, bucket = deal_from_median(175000, 130000)
        self.assertLess(score, 0)
        self.assertEqual(bucket, "Premium")


if __name__ == "__main__":
    unittest.main()
