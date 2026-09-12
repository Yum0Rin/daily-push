"""promote_reserve: un-hide reserve items to refill shown slots."""
import unittest

from daily_push.backfill import promote_reserve


class BackfillTest(unittest.TestCase):
    def test_promotes_hidden_to_fill(self):
        items = [{"id": 1}, {"id": 2, "hidden": True}, {"id": 3, "hidden": True}]
        promote_reserve(items, 2)
        self.assertNotIn("hidden", items[1])
        self.assertTrue(items[2].get("hidden"))

    def test_no_promotion_when_full(self):
        items = [{"id": 1}, {"id": 2}, {"id": 3, "hidden": True}]
        promote_reserve(items, 2)
        self.assertTrue(items[2].get("hidden"))

    def test_target_zero(self):
        items = [{"id": 1}, {"id": 2, "hidden": True}]
        promote_reserve(items, 0)
        self.assertTrue(items[1].get("hidden"))


if __name__ == "__main__":
    unittest.main()
