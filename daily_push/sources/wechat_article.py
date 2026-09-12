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
        self.max_articles = int(c.get("max_articles", 12))
        self.mp_cutoff_hour = int(c.get("mp_cutoff_hour", 18))
        self.reserve = int(c.get("reserve", 3))

    def _is_excluded(self, author, title=""):
        """公众号屏蔽只按作者（公众号名）做子串匹配。

        ``title`` 仅为保留参数，**不参与匹配**——避免标题里出现关键词时误伤
        正常推文（如标题含「通知」但账号本身需要保留）。
        """
        return any(k in author for k in self.exclude_keywords)

    def _window(self):
        """推送窗口：最近一次「18:00 截止点」之后的 24h ~ 当前时刻（北京时间）。

        起始 = 最近已结束那天 18:00:01（如晚上采 → 前一天 18:00:01；早上采 → 前天 18:00:01），
        结束 = 现在（当天更晚的新文章也会被采进来）。
        重复推送由 collector 的跨天去重（cutoffs.json）兜底。
        """
        tz = datetime.timezone(datetime.timedelta(hours=8))
        now = datetime.datetime.now(tz)
        boundary = now.replace(hour=self.mp_cutoff_hour, minute=0, second=0, microsecond=0)
        if now < boundary:
            boundary -= datetime.timedelta(days=1)
        start = boundary - datetime.timedelta(days=1) + datetime.timedelta(seconds=1)
        return int(start.timestamp()), int(now.timestamp())

    def _ctx(self):
        from wechat_cli_mcp.context import get_context
        return get_context()

    @staticmethod
    def _cover_from_text(text):
        """Extract the article cover URL from the raw appmsg XML (best effort).

        WeChat stores several variants; prefer 16:9, then the chat thumbnail.
        """
        for tag in ("cover_16_9", "thumburl", "cover_235_1", "cover_1_1"):
            m = re.search(r"<%s>(?:<!\[CDATA\[)?(https?://[^\]<\s]+)" % tag, text or "")
            if m:
                return m.group(1).replace("http://", "https://", 1)
        return ""

    @staticmethod
    def _parse_appmsg(text):
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
        return {"title": title, "url": url, "author": author,
                "pic": WeChatArticleCollector._cover_from_text(text)}

    def _collect_from_one_db(self, decompress_content, rel):
        """Scan all Msg_* tables in one biz db for recent articles."""
        ctx = self._ctx()
        path = ctx.cache.get(rel)
        if not path:
            return []
        start_ts, end_ts = self._window()
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
                            f"WHERE create_time >= ? AND create_time <= ? "
                            f"ORDER BY create_time DESC LIMIT 50",
                            (int(start_ts), int(end_ts)),
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
                            if self._is_excluded(author, title):
                                continue
                            articles.append({
                                "title": title,
                                "url": parsed["url"],
                                "author": author,
                                "pic": parsed.get("pic", ""),
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
        ctx = self._ctx()
        import glob
        # 动态发现全部公众号库（biz_message_*.db），避免新库出现后漏采
        dbs = sorted(glob.glob(os.path.join(ctx.db_dir, "message", "biz_message_*.db")))
        articles = []
        for path in dbs:
            rel = "message/" + os.path.basename(path)
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
        if self.max_articles:
            unique = unique[: self.max_articles + max(0, self.reserve)]
            for i, a in enumerate(unique):
                if i >= self.max_articles:
                    a["hidden"] = True
        return unique

    def cover_map(self, since_ts=0, per_table_limit=2000):
        """Return {article_url: cover_url} scanned from local WeChat DBs.

        Used to backfill covers on already-collected history (local only, no
        external requests).
        """
        from wechat_cli_mcp.core.messages import decompress_content
        import glob
        ctx = self._ctx()
        dbs = sorted(glob.glob(os.path.join(ctx.db_dir, "message", "biz_message_*.db")))
        out = {}
        for path in dbs:
            rel = "message/" + os.path.basename(path)
            db = ctx.cache.get(rel)
            if not db:
                continue
            try:
                with closing(sqlite3.connect(db)) as conn:
                    tables = [r[0] for r in conn.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name LIKE 'Msg_%'")]
                    for t in tables:
                        try:
                            rows = conn.execute(
                                f"SELECT WCDB_CT_message_content, message_content FROM [{t}] "
                                f"WHERE create_time >= ? ORDER BY create_time DESC LIMIT ?",
                                (int(since_ts), int(per_table_limit))).fetchall()
                        except Exception:
                            continue
                        for ct_flag, content in rows:
                            if not content:
                                continue
                            text = decompress_content(content, ct_flag) if ct_flag == 4 else content
                            if isinstance(text, bytes):
                                text = text.decode("utf-8", "ignore")
                            parsed = self._parse_appmsg(text)
                            if parsed and parsed.get("pic"):
                                out.setdefault(parsed["url"], parsed["pic"])
            except Exception:
                pass
        return out

    def scan_all(self, since_ts=0, per_table_limit=5000):
        """Return all appmsg articles since ``since_ts`` (local DB, no network)."""
        from wechat_cli_mcp.core.messages import decompress_content
        import glob
        ctx = self._ctx()
        dbs = sorted(glob.glob(os.path.join(ctx.db_dir, "message", "biz_message_*.db")))
        out = []
        for path in dbs:
            rel = "message/" + os.path.basename(path)
            db = ctx.cache.get(rel)
            if not db:
                continue
            try:
                with closing(sqlite3.connect(db)) as conn:
                    tables = [r[0] for r in conn.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name LIKE 'Msg_%'")]
                    for t in tables:
                        try:
                            rows = conn.execute(
                                f"SELECT create_time, WCDB_CT_message_content, message_content "
                                f"FROM [{t}] WHERE create_time >= ? "
                                f"ORDER BY create_time DESC LIMIT ?",
                                (int(since_ts), int(per_table_limit))).fetchall()
                        except Exception:
                            continue
                        for ct, ct_flag, content in rows:
                            if not content:
                                continue
                            text = decompress_content(content, ct_flag) if ct_flag == 4 else content
                            if isinstance(text, bytes):
                                text = text.decode("utf-8", "ignore")
                            parsed = self._parse_appmsg(text)
                            if not parsed:
                                continue
                            if any(k in parsed["author"] for k in self.exclude_keywords):
                                continue
                            out.append({
                                "title": parsed["title"],
                                "url": parsed["url"],
                                "author": parsed["author"],
                                "pic": parsed.get("pic", ""),
                                "notify": any(k in parsed["title"] for k in self.notify_keywords),
                                "time": datetime.datetime.fromtimestamp(
                                    ct).strftime("%m-%d %H:%M"),
                                "timestamp": int(ct),
                            })
            except Exception:
                pass
        return out