"""抖音推荐流筛选逻辑（标签屏蔽 / AI 启发式 / 点赞 / 藏赞比）。"""
import unittest

from daily_push.sources.douyin import (
    DEFAULT_AI_KEYWORDS,
    DEFAULT_BLOCKED_TAGS,
    DouyinCollector,
    is_blocked_entry,
)


def _collector(**over):
    cfg = {"douyin": {"cookie": "sessionid=x", "limit": 10, "request_interval": 0,
                      "time_budget": 30, "max_pages": 3}}
    cfg["douyin"].update(over)
    return DouyinCollector(cfg)


def _item(aid="7697586688307094181", digg=100000, collect=20000, tags=("音乐",),
          hashtags=(), desc="一条普通视频", ads=False, life=False, author="作者"):
    return {
        "aweme_id": aid,
        "desc": desc,
        "item_title": desc,
        "create_time": 1792234063,
        "is_ads": ads,
        "is_life_item": life,
        "media_type": 4,
        "author": {"nickname": author, "sec_uid": "MS4wLjABAAAAxxx"},
        "statistics": {"digg_count": digg, "collect_count": collect,
                       "comment_count": 100, "share_count": 50, "play_count": 0},
        "video": {"duration": 22000,
                  "cover": {"url_list": ["http://p3.douyinpic.com/x.jpg"]}},
        "video_tag": [{"tag_name": t} for t in tags],
        "text_extra": [{"hashtag_name": h} for h in hashtags],
    }


class TagFilterTest(unittest.TestCase):
    def test_blocked_video_tag(self):
        c = _collector()
        self.assertTrue(c._dropped(_item(tags=("游戏", "单机游戏"))))
        self.assertTrue(c._dropped(_item(tags=("随拍", "唠嗑"))))

    def test_blocked_hashtag(self):
        c = _collector()
        self.assertTrue(c._dropped(_item(hashtags=("抽象",))))
        self.assertTrue(c._dropped(_item(hashtags=("零基础学习",))))

    def test_vibe_is_case_insensitive(self):
        c = _collector()
        self.assertTrue(c._dropped(_item(hashtags=("Vibe",))))

    def test_normal_kept(self):
        c = _collector()
        self.assertFalse(c._dropped(_item(tags=("音乐",), hashtags=("钢琴",))))

    def test_empty_list_disables(self):
        c = _collector(blocked_tags=[])
        self.assertFalse(c._dropped(_item(tags=("游戏",))))

    def test_defaults_present(self):
        for k in ("游戏", "娱", "热点", "vibe", "英语", "抽象", "推荐", "唠嗑",
                  "零基础", "抖音", "华语乐坛", "讲解", "作文", "AI"):
            self.assertIn(k, DEFAULT_BLOCKED_TAGS)


class AiFilterTest(unittest.TestCase):
    def test_ai_keywords_drop(self):
        c = _collector()
        self.assertTrue(c._dropped(_item(desc="这条是AI生成的短片")))
        self.assertTrue(c._dropped(_item(hashtags=("aigc",))))

    def test_empty_ai_list_disables(self):
        # 只清空 ai_keywords 时，标题里的「AI」仍会被 blocked_tags 里的 AI 挡掉
        c = _collector(ai_keywords=[])
        self.assertTrue(c._dropped(_item(desc="这条是AI生成的短片")))
        # 两处都清空才彻底关闭
        c2 = _collector(ai_keywords=[], blocked_tags=[])
        self.assertFalse(c2._dropped(_item(desc="这条是AI生成的短片")))

    def test_defaults_present(self):
        self.assertIn("aigc", DEFAULT_AI_KEYWORDS)


class StoredEntryFilterTest(unittest.TestCase):
    """清理历史时复用同一套规则（`is_blocked_entry`），防止两边口径漂移。"""

    def test_blocked_by_tag(self):
        e = {"title": "普通标题", "author": "作者", "tags": ["讲解", "知识"]}
        self.assertTrue(is_blocked_entry(e))
        e2 = {"title": "普通标题", "author": "作者", "tags": ["作文"]}
        self.assertTrue(is_blocked_entry(e2))

    def test_blocked_in_title(self):
        e = {"title": "【作文55+】每天睁开眼", "author": "作者", "tags": ["校园教育"]}
        self.assertTrue(is_blocked_entry(e))
        e2 = {"title": "【深度讲解】流水不争先", "author": "作者", "tags": ["人文社科"]}
        self.assertTrue(is_blocked_entry(e2))

    def test_ai_title_is_case_sensitive(self):
        self.assertTrue(is_blocked_entry({"title": "AI绘画教程", "tags": ["科技"]}))
        # 英文单词里的 ai 不算（again / said）
        self.assertFalse(is_blocked_entry({"title": "You know how I do it again", "tags": ["舞蹈"]}))
        # 话题/标签仍忽略大小写
        self.assertTrue(is_blocked_entry({"title": "普通", "tags": ["aigc"]}))

    def test_normal_entry_kept(self):
        e = {"title": "一段舞蹈", "author": "某某", "tags": ["舞蹈", "街舞"]}
        self.assertFalse(is_blocked_entry(e))

    def test_custom_lists(self):
        e = {"title": "普通标题", "author": "作者", "tags": ["舞蹈"]}
        self.assertFalse(is_blocked_entry(e, blocked_tags=[]))
        self.assertTrue(is_blocked_entry(e, exclude_keywords=["作者"]))


class CollectFilterTest(unittest.TestCase):
    def _run(self, items, **over):
        cfg = {"douyin": {"cookie": "sessionid=x", "limit": 6, "min_digg": 20000,
                          "min_collect_ratio": 0.08, "request_interval": 0,
                          "time_budget": 30, "max_pages": 3}}
        cfg["douyin"].update(over)
        c = DouyinCollector(cfg)
        c._cookies = {"sessionid": "x"}
        c._page = lambda idx: items
        return c.collect()

    def test_min_digg(self):
        out = self._run([_item("1111111111111111111", digg=19999, collect=9999)])
        self.assertEqual(out, [])

    def test_collect_ratio(self):
        # 20000 赞 800 收藏 = 4%，低于 8%
        out = self._run([_item("1111111111111111111", digg=20000, collect=800)])
        self.assertEqual(out, [])
        # 20000 赞 2000 收藏 = 10%，通过
        out = self._run([_item("2222222222222222222", digg=20000, collect=2000)])
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[0]["collect_ratio"], 0.1)

    def test_ads_and_life_dropped(self):
        items = [_item("1111111111111111111", ads=True),
                 _item("2222222222222222222", life=True)]
        self.assertEqual(self._run(items), [])

    def test_limit_and_order(self):
        items = [_item(str(1000000000000000000 + i), digg=100000 + i, collect=20000)
                 for i in range(10)]
        out = self._run(items, limit=6)
        self.assertEqual(len(out), 6)
        self.assertEqual(out[0]["id"], "1000000000000000000")

    def test_exclude_pushed_urls(self):
        url = "https://www.douyin.com/video/1111111111111111111"
        out = self._run([_item("1111111111111111111")], )
        self.assertEqual(len(out), 1)
        c = _collector(limit=6, min_collect_ratio=0.08)
        c._cookies = {"sessionid": "x"}
        c._page = lambda idx: [_item("1111111111111111111")]
        self.assertEqual(c.collect(exclude_urls={url}), [])

    def test_entry_fields(self):
        out = self._run([_item("1111111111111111111", digg=100000, collect=20000)])
        e = out[0]
        self.assertEqual(e["url"], "https://www.douyin.com/video/1111111111111111111")
        self.assertEqual(e["digg"], 100000)
        self.assertEqual(e["collect"], 20000)
        self.assertEqual(e["author"], "作者")
        self.assertEqual(e["duration"], 22)
        self.assertTrue(e["pic"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
