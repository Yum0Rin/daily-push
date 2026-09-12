"""Bilibili ignore matching: substring, and empty entries must not match all."""
import unittest

from daily_push.sources.bilibili import BiliCollector


class BiliFilterTest(unittest.TestCase):
    def _c(self, exclude):
        return BiliCollector({"bilibili": {"exclude": exclude}})

    def test_substring_match(self):
        self.assertTrue(self._c(["冷水"])._is_excluded("冷水先森无人声助眠"))

    def test_empty_entry_is_ignored(self):
        self.assertFalse(self._c([""])._is_excluded("任意UP"))

    def test_non_match(self):
        self.assertFalse(self._c(["冷水"])._is_excluded("别人的视频"))


if __name__ == "__main__":
    unittest.main()
