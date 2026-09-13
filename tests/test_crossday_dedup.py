"""跨天去重：已推过的 URL 不再重复推送（微信 / B站）。"""
import time
import unittest

from daily_push.sources.bilibili import BiliCollector
from daily_push.sources.wechat_article import WeChatArticleCollector


class WeChatExcludeUrlsTest(unittest.TestCase):
    def _c(self, **kw):
        return WeChatArticleCollector({"wechat": kw})

    def _arts(self, n):
        return [
            {"url": f"u{i}", "timestamp": 1000 - i, "title": f"t{i}", "notify": False}
            for i in range(n)
        ]

    def test_excluded_urls_dropped(self):
        c = self._c(max_articles=10, reserve=0)
        out = c._assemble(self._arts(4), exclude_urls={"u0", "u2"})
        self.assertEqual([a["url"] for a in out], ["u1", "u3"])

    def test_reserve_refilled_after_exclusion(self):
        # u0/u1 已推过 → u2/u3 顶上来，u4 仍作隐藏缓冲
        c = self._c(max_articles=2, reserve=2)
        out = c._assemble(self._arts(5), exclude_urls={"u0", "u1"})
        self.assertEqual([a["url"] for a in out], ["u2", "u3", "u4"])
        self.assertNotIn("hidden", out[0])
        self.assertNotIn("hidden", out[1])
        self.assertTrue(out[2].get("hidden"))

    def test_no_exclude_keeps_all(self):
        c = self._c(max_articles=10, reserve=0)
        out = c._assemble(self._arts(3))
        self.assertEqual(len(out), 3)


class _FakeBili(BiliCollector):
    def __init__(self, items):
        super().__init__({"bilibili": {"max_videos": 10, "reserve": 0, "recent_days": 7}})
        self.sessdata = "x"
        self._items = items

    def _get(self, url, params=None, wbi=False):
        return {"data": {"items": self._items, "has_more": False}}


def _bili_item(bvid, ts, name="UP"):
    return {
        "type": "DYNAMIC_TYPE_AV",
        "modules": {
            "module_author": {"name": name, "pub_ts": ts},
            "module_dynamic": {
                "major": {"archive": {"bvid": bvid, "title": "T", "cover": ""}}
            },
        },
    }


class BiliExcludeUrlsTest(unittest.TestCase):
    def test_excluded_urls_dropped(self):
        now = int(time.time())
        items = [_bili_item("BV1", now), _bili_item("BV2", now), _bili_item("BV3", now)]
        c = _FakeBili(items)
        out = c.collect(exclude_urls={"https://www.bilibili.com/video/BV2"})
        self.assertEqual([e["url"] for e in out],
                         ["https://www.bilibili.com/video/BV1",
                          "https://www.bilibili.com/video/BV3"])

    def test_no_exclude_keeps_all(self):
        now = int(time.time())
        c = _FakeBili([_bili_item("BV1", now), _bili_item("BV2", now)])
        self.assertEqual(len(c.collect()), 2)


if __name__ == "__main__":
    unittest.main()
