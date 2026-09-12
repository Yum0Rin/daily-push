"""cover_backfill pure helpers."""
import unittest

from daily_push.cover_backfill import _bvid, _https, _is_invalid


class CoverBackfillHelpersTest(unittest.TestCase):
    def test_https(self):
        self.assertEqual(_https("http://i1.hdslb.com/x.jpg"), "https://i1.hdslb.com/x.jpg")
        self.assertEqual(_https("https://a/b"), "https://a/b")
        self.assertEqual(_https(""), "")

    def test_bvid(self):
        self.assertEqual(_bvid("https://www.bilibili.com/video/BV1xx411c7mD"), "BV1xx411c7mD")
        self.assertIsNone(_bvid("https://example.com/x"))

    def test_is_invalid(self):
        self.assertTrue(_is_invalid(-404))
        self.assertTrue(_is_invalid(-403))
        self.assertTrue(_is_invalid(62012))
        self.assertTrue(_is_invalid(62002))
        self.assertFalse(_is_invalid(0))
        self.assertFalse(_is_invalid(-799))  # 限流不算失效
        self.assertFalse(_is_invalid(None))


if __name__ == "__main__":
    unittest.main()
