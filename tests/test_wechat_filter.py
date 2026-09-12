"""WeChat ignore matching must be author-only (substring), never title."""
import unittest

from daily_push.sources.wechat_article import WeChatArticleCollector


class WeChatExcludeTest(unittest.TestCase):
    def _c(self, kws):
        return WeChatArticleCollector({"wechat": {"exclude_keywords": kws}})

    def test_author_substring_match(self):
        c = self._c(["共青团"])
        self.assertTrue(c._is_excluded("共青团中央"))
        self.assertTrue(c._is_excluded("江西共青团"))  # substring, not exact

    def test_title_is_never_matched(self):
        c = self._c(["共青团"])
        self.assertFalse(c._is_excluded("某正常公众号", "共青团喊你学习"))

    def test_non_match(self):
        c = self._c(["共青团"])
        self.assertFalse(c._is_excluded("人民日报", "今日要闻"))


class WeChatCoverTest(unittest.TestCase):
    def _parse(self, xml):
        return WeChatArticleCollector._parse_appmsg(xml)

    def test_cover_extracted_and_https(self):
        xml = ("<msg><appmsg><title>T</title>"
               "<url>https://mp.weixin.qq.com/s?x</url>"
               "<thumburl><![CDATA[http://mmbiz.qpic.cn/a.jpg]]></thumburl>"
               "</appmsg></msg>")
        self.assertEqual(self._parse(xml)["pic"], "https://mmbiz.qpic.cn/a.jpg")

    def test_cover_prefers_16_9(self):
        xml = ("<msg><appmsg><title>T</title><url>https://mp.weixin.qq.com/s?x</url>"
               "<cover_16_9><![CDATA[https://x/169.jpg]]></cover_16_9>"
               "<thumburl><![CDATA[https://x/t.jpg]]></thumburl>"
               "</appmsg></msg>")
        self.assertEqual(self._parse(xml)["pic"], "https://x/169.jpg")

    def test_no_cover(self):
        xml = ("<msg><appmsg><title>T</title>"
               "<url>https://mp.weixin.qq.com/s?x</url></appmsg></msg>")
        self.assertEqual(self._parse(xml)["pic"], "")


if __name__ == "__main__":
    unittest.main()
