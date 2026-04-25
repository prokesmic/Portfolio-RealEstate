import unittest

from backend.geography import distance_to_bedrichov, is_jizerske_hory_locality


class GeographyTests(unittest.TestCase):
    def test_distance_to_bedrichov(self) -> None:
        self.assertIsNotNone(distance_to_bedrichov(50.7914, 15.1426))
        self.assertAlmostEqual(distance_to_bedrichov(50.7914, 15.1426) or 0, 0.0, places=2)

    def test_is_jizerske_hory_locality(self) -> None:
        self.assertTrue(is_jizerske_hory_locality("Bedrichov"))
        self.assertTrue(is_jizerske_hory_locality("Jablonec nad Nisou"))
        self.assertFalse(is_jizerske_hory_locality("Praha 3 - Zizkov", 50.084, 14.462))


if __name__ == "__main__":
    unittest.main()
