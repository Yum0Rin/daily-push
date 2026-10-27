"""B站首页推荐的阈值/屏蔽判定（纯函数，不联网）。"""
import unittest

from daily_push.sources.bilibili import BiliRecommendCollector


def _collector(**rec):
    cfg = {"bilibili": {"sessdata": "x", "recommend": dict({
        "min_views": 50000, "min_like_ratio": 0.07, "limit": 10, "max_pages": 8,
    }, **rec)}}
    return BiliRecommendCollector(cfg)


def _item(**over):
    it = {
        "goto": "av", "bvid": "BV1xx411c7mD", "title": "标题",
        "owner": {"name": "某UP"}, "is_followed": 0,
        "stat": {"view": 100000, "like": 10000}, "pubdate": 1793000000,
        "duration": 100, "pic": "http://i0.hdslb.com/a.jpg",
        "rcmd_reason": {"reason_type": 0},
    }
    it.update(over)
    return it


class RecommendFilterTest(unittest.TestCase):
    def test_pass(self):
        e = _collector()._to_entry(_item())
        self.assertIsNotNone(e)
        self.assertEqual(e["ratio"], 0.1)
        self.assertEqual(e["url"], "https://www.bilibili.com/video/BV1xx411c7mD")
        self.assertTrue(e["pic"].startswith("https://"))

    def test_followed_skipped(self):
        self.assertIsNone(_collector()._to_entry(_item(is_followed=1)))

    def test_views_must_be_strictly_greater(self):
        self.assertIsNone(_collector()._to_entry(_item(stat={"view": 50000, "like": 10000})))
        self.assertIsNotNone(_collector()._to_entry(_item(stat={"view": 50001, "like": 10000})))

    def test_ratio_must_be_strictly_greater(self):
        # 7000/100000 = 0.07，等于阈值 -> 丢弃
        self.assertIsNone(_collector()._to_entry(_item(stat={"view": 100000, "like": 7000})))
        self.assertIsNotNone(_collector()._to_entry(_item(stat={"view": 100000, "like": 7001})))

    def test_non_video_skipped(self):
        self.assertIsNone(_collector()._to_entry(_item(goto="live")))

    def test_ad_reason_skipped(self):
        it = _item(rcmd_reason={"reason_type": 9, "content": "广告"})
        self.assertIsNone(_collector()._to_entry(it))

    def test_excluded_author(self):
        cfg = {"bilibili": {"sessdata": "x", "exclude": ["某UP"]}}
        self.assertIsNone(BiliRecommendCollector(cfg)._to_entry(_item()))

    def test_thresholds_are_configurable(self):
        c = _collector(min_views=1000, min_like_ratio=0.01)
        self.assertIsNotNone(c._to_entry(_item(stat={"view": 2000, "like": 100})))

    def test_missing_stat(self):
        self.assertIsNone(_collector()._to_entry(_item(stat={})))


if __name__ == "__main__":
    unittest.main()
