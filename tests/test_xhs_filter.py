"""小红书采集的纯函数过滤逻辑（不联网）。"""
import unittest

from daily_push.sources.xiaohongshu import (
    DEFAULT_AD_KEYWORDS,
    XhsCollector,
    _parse_likes,
)


def _collector(**over):
    cfg = {"xiaohongshu": {"cookie": "web_session=x", "limit": 10}}
    cfg["xiaohongshu"].update(over)
    return XhsCollector(cfg)


class ParseLikesTest(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(_parse_likes("549"), 549)

    def test_wan(self):
        self.assertEqual(_parse_likes("1.1万"), 11000)
        self.assertEqual(_parse_likes("10万"), 100000)

    def test_qian(self):
        self.assertEqual(_parse_likes("2.3千"), 2300)

    def test_bad(self):
        self.assertEqual(_parse_likes(""), 0)
        self.assertEqual(_parse_likes(None), 0)
        self.assertEqual(_parse_likes("赞"), 0)


class CreatedTest(unittest.TestCase):
    def test_from_note_id(self):
        # 6adcbeb4 = 2026-10-27 前后
        self.assertEqual(XhsCollector._created("6adcbeb40000000033013bff"), 0x6ADCBEB4)

    def test_bad_id(self):
        self.assertEqual(XhsCollector._created("zzzz"), 0)
        self.assertEqual(XhsCollector._created(""), 0)


class AdFilterTest(unittest.TestCase):
    def test_default_keywords_drop_ads(self):
        c = _collector()
        self.assertTrue(c._is_dropped("好物分享｜品牌合作", "某某"))
        self.assertTrue(c._is_dropped("今天吃了什么", "某某旗舰店"))

    def test_normal_note_kept(self):
        c = _collector()
        self.assertFalse(c._is_dropped("工科女的主线任务", "最懵的柿子"))

    def test_empty_list_disables_ad_filter(self):
        c = _collector(ad_keywords=[])
        self.assertFalse(c._is_dropped("品牌合作 广告", "旗舰店"))

    def test_extra_exclude_keywords(self):
        c = _collector(exclude_keywords=["原神"])
        self.assertTrue(c._is_dropped("原神新角色", "玩家"))
        self.assertFalse(c._is_dropped("别的游戏", "玩家"))

    def test_defaults_present(self):
        self.assertIn("广告", DEFAULT_AD_KEYWORDS)


class CoverTest(unittest.TestCase):
    def test_info_list_fallback_and_https(self):
        card = {"cover": {"url": "", "info_list": [
            {"image_scene": "FD_WM_WEBP", "url": "http://a/b.jpg"},
            {"image_scene": "FD_PRV_WEBP", "url": "http://a/c.jpg"},
        ]}}
        self.assertEqual(XhsCollector._cover(card), "https://a/c.jpg")

    def test_missing_cover(self):
        self.assertEqual(XhsCollector._cover({}), "")


def _note(nid, likes, title="普通笔记", author="作者"):
    return {
        "id": nid,
        "xsec_token": "tok",
        "note_card": {
            "display_title": title,
            "user": {"nickname": author},
            "interact_info": {"liked_count": likes},
            "type": "normal",
            "cover": {"url": "http://a/b.jpg"},
        },
    }


class CollectRatioTest(unittest.TestCase):
    """藏/赞比过滤（详情接口用桩替换，不联网）。"""

    def _run(self, notes, detail, **over):
        cfg = {"xiaohongshu": {"cookie": "web_session=x", "limit": 10,
                               "detail_interval": 0}}
        cfg["xiaohongshu"].update(over)
        c = XhsCollector(cfg)
        c._cookies = {"web_session": "x", "a1": "y"}
        c._page = lambda cursor: (notes, "")
        c._detail = detail
        return c.collect()

    def test_below_ratio_dropped(self):
        notes = [_note("6adcbeb40000000033013bff", "6000")]
        out = self._run(notes, lambda nid, tok: {"liked_count": "6000",
                                                 "collected_count": "120"},
                        min_collect_ratio=0.04)  # 0.02 < 0.04
        self.assertEqual(out, [])

    def test_above_ratio_kept_with_fields(self):
        notes = [_note("6adcbeb40000000033013bff", "6000")]
        out = self._run(notes, lambda nid, tok: {"liked_count": "8000",
                                                 "collected_count": "800"},
                        min_collect_ratio=0.04)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["collects"], 800)
        self.assertAlmostEqual(out[0]["collect_ratio"], 0.1)
        self.assertEqual(out[0]["likes"], 8000)  # 以详情为准

    def test_detail_failure_keeps_note(self):
        notes = [_note("6adcbeb40000000033013bff", "6000")]
        out = self._run(notes, lambda nid, tok: None, min_collect_ratio=0.04)
        self.assertEqual(len(out), 1)
        self.assertIsNone(out[0]["collect_ratio"])

    def test_zero_threshold_skips_detail(self):
        calls = []
        notes = [_note("6adcbeb40000000033013bff", "6000")]

        def detail(nid, tok):
            calls.append(nid)
            return {"liked_count": "6000", "collected_count": "1"}

        out = self._run(notes, detail, min_collect_ratio=0)
        self.assertEqual(len(out), 1)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
