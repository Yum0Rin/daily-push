"""微信公众号推文采集（仅标题 + 链接）.

读取微信解密后的 biz_message_*.db，提取公众号推送文章（appmsg）的
<title> 与 <url>，按发布时间倒序取最近 N 条。
复用 chat-mcp 的 wechat_cli_mcp 解密/解压模块。
"""
import datetime
import os
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from contextlib import closing

WMCP_DIR = (
    os.environ.get("WMCP_DIR")
    or r"C:\Users\39007\chat-mcp\wechat-mcp-server"
)
if WMCP_DIR not in sys.path:
    sys.path.insert(0, WMCP_DIR)


class WeChatError(Exception):
    pass


class WeChatArticleCollector:
    def __init__(self, cfg):
        c = cfg.get("wechat", {})
        self.important_biz = [str(k) for k in (c.get("important_biz") or [])]
        self.exclude_keywords = [str(k) for k in (
            c.get("exclude_keywords")
            or ["演出余票监控", "省教育厅", "三福sanfu"])]
        self.notify_keywords = [str(k) for k in (
            c.get("notify_keywords")
            or ["提醒", "通知", "签收", "到账", "取餐", "下单", "已支付",
                "排队", "发货", "日报", "账单", "领取", "优惠券"])]
        self.max_articles = int(c.get("max_articles", 10))
        self.days = int(c.get("article_days", 7))

    def _ctx(self):
        from wechat_cli_mcp.context import get_context
        return get_context()

    @staticmethod
    def _parse_appmsg(text):
        """Extract (title, url, author) from appmsg xml blob, else None."""
        if not text or "<appmsg" not in text:
            return None
        # guard against entity expansion (ET will not expand externals, but be safe)
        try:
            assert not re.search(r"<!DOCTYPE|<!ENTITY", text, re.I)
            root = ET.fromstring(text[:20000])
        except Exception:
            return None
        app = root.find(".//appmsg")
        if app is None:
            return None
        title = (app.findtext("title") or "").strip()
        url = (app.findtext("url") or "").strip()
        if not title or not url or not url.startswith("http"):
            return None
        author = ""
        cat = app.find(".//mmreader/category/name")
        if cat is not None and cat.text:
            author = cat.text.strip()
        if not author:
            src = app.find(".//mmreader/category/item/sources/source/name")
            if src is not None and src.text:
                author = src.text.strip()
        return {"title": title, "url": url, "author": author}

    def _collect_from_one_db(self, decompress_content, rel):
        """Scan all Msg_* tables in one biz db for recent articles."""
        ctx = self._ctx()
        path = ctx.cache.get(rel)
        if not path:
            return []
        cutoff = (datetime.datetime.now()
                  - datetime.timedelta(days=self.days)).timestamp()
        articles = []
        try:
            with closing(sqlite3.connect(path)) as conn:
                tables = [
                    r[0] for r in conn.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name LIKE 'Msg_%'")
                ]
                for t in tables:
                    try:
                        rows = conn.execute(
                            f"SELECT create_time, WCDB_CT_message_content, "
                            f"message_content FROM [{t}] "
                            f"WHERE create_time >= ? ORDER BY create_time DESC LIMIT 50",
                            (int(cutoff),),
                        ).fetchall()
                    except Exception:
                        continue
                    for ct, ct_flag, content in rows:
                        if not content:
                            continue
                        text = decompress_content(content, ct_flag) if ct_flag == 4 else content
                        if isinstance(text, bytes):
                            text = text.decode("utf-8", "ignore")
                        parsed = self._parse_appmsg(text)
                        if parsed:
                            title = parsed["title"]
                            author = parsed["author"]
                            if any(k in author or k in title for k in self.exclude_keywords):
                                continue
                            articles.append({
                                "title": title,
                                "url": parsed["url"],
                                "author": author,
                                "notify": any(k in title for k in self.notify_keywords),
                                "time": datetime.datetime.fromtimestamp(
                                    ct).strftime("%m-%d %H:%M"),
                                "timestamp": int(ct),
                            })
        except Exception:
            pass
        return articles

    def collect(self):
        from wechat_cli_mcp.core.messages import decompress_content
        articles = []
        for rel in ("message/biz_message_0.db", "message/biz_message_1.db"):
            articles += self._collect_from_one_db(decompress_content, rel)
        # dedupe by url; content first, notifications below, both by time desc
        seen, unique = set(), []
        for a in sorted(articles, key=lambda x: (x.get("notify", False), -x["timestamp"])):
            if a["url"] in seen:
                continue
            seen.add(a["url"])
            unique.append(a)
        if self.important_biz:
            unique = [a for a in unique
                      if any(k in a["title"] for k in self.important_biz)]
        return unique[: self.max_articles]