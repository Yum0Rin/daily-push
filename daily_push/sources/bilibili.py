"""Bilibili 采集：关注动态 + 首页推荐.

关注动态：通过「关注动态」接口 (x/polymer/web-dynamic/v1/feed/all?type=video)
一次拉取最近投稿的视频（标题/链接/UP名/发布时间），再按窗口过滤，无需逐个访问 UP 空间。

首页推荐：通过 (x/web-interface/index/top/feed/rcmd) 拉个性化推荐流，接口自带
``is_followed`` 与 ``stat.view/like``，可按「未关注 + 播放量 + 点赞率」筛选。

Requires a logged-in SESSDATA cookie (stored in config.json).
"""
import datetime
import hashlib
import time

import requests
_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


class BiliError(Exception):
    pass


class BiliCollector:
    def __init__(self, cfg):
        bili = cfg.get("bilibili", {})
        self.sessdata = bili.get("sessdata") or ""
        self.exclude = [str(n) for n in (bili.get("exclude") or [])]
        self.recent_days = int(bili.get("recent_days", 1))
        self.max_videos = int(bili.get("max_videos", 10))
        self.feed_pages = int(bili.get("feed_pages", 2))
        self.reserve = int(bili.get("reserve", 3))
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
        })
        if self.sessdata:
            self.session.cookies.set("SESSDATA", self.sessdata, domain=".bilibili.com")
        self._img_key = None
        self._sub_key = None

    def _is_excluded(self, name):
        """True if the UP name matches any exclude entry (substring; empties ignored)."""
        return any(k and k in name for k in self.exclude)

    # ---- WBI signing ----
    def _get_wbi_keys(self):
        if self._img_key and self._sub_key:
            return self._img_key, self._sub_key
        try:
            r = self.session.get("https://api.bilibili.com/x/web-interface/nav", timeout=15)
            data = r.json()
            wbi = data["data"]["wbi_img"]
            self._img_key = wbi["img_url"].rsplit("/", 1)[-1].split(".")[0]
            self._sub_key = wbi["sub_url"].rsplit("/", 1)[-1].split(".")[0]
        except Exception as e:
            raise BiliError(f"cannot fetch wbi keys: {e}")
        return self._img_key, self._sub_key

    @staticmethod
    def _mixin_key(orig):
        return "".join(orig[i] for i in _MIXIN_KEY_ENC_TAB if i < len(orig))[:32]

    def _enc_wbi(self, params):
        img_key, sub_key = self._get_wbi_keys()
        mixin = self._mixin_key(img_key + sub_key)
        params = dict(params or {})
        params["wts"] = int(time.time())
        params = {k: str(v) for k, v in sorted(params.items()) if str(v) != ""}
        query = "&".join(f"{k}={v}" for k, v in params.items())
        params["w_rid"] = hashlib.md5((query + mixin).encode()).hexdigest()
        return params

    def _get(self, url, params=None, wbi=False, retries=3):
        params = dict(params or {})
        if wbi:
            params = self._enc_wbi(params)
        last = None
        for attempt in range(1, retries + 1):
            try:
                r = self.session.get(url, params=params, timeout=15)
            except Exception as e:
                last = BiliError(f"request failed: {e}")
                time.sleep(2 * attempt)
                continue
            if r.status_code == 412 or "text/html" in (r.headers.get("content-type") or ""):
                # risk control page -> back off and retry
                last = BiliError(
                    "risk-control (HTTP 412) 被风控，稍后再试" if r.status_code == 412
                    else f"unexpected HTML response (HTTP {r.status_code})")
                time.sleep(3 * attempt)
                continue
            try:
                data = r.json()
            except Exception as e:
                last = BiliError(f"bad json (HTTP {r.status_code}): {e}")
                time.sleep(2 * attempt)
                continue
            if data.get("code") != 0:
                raise BiliError(f"api error {data.get('code')}: {data.get('message')}")
            return data
        raise last or BiliError("request failed")

    def collect(self, exclude_urls=None):
        if not self.sessdata:
            raise BiliError("bilibili sessdata not configured")
        exclude_urls = exclude_urls or set()
        cutoff = datetime.datetime.combine(
            datetime.date.today() - datetime.timedelta(days=self.recent_days),
            datetime.time.min).timestamp()
        limit = (self.max_videos + max(0, self.reserve)) if self.max_videos else 0  # 0=不限
        entries, seen_bvid, offset = [], set(), ""
        for _ in range(self.feed_pages):
            params = {"type": "video"}
            if offset:
                params["offset"] = offset
            data = self._get(
                "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/all",
                params=params, wbi=True).get("data", {})
            items = data.get("items") or []
            for it in items:
                if it.get("type") != "DYNAMIC_TYPE_AV":
                    continue
                mods = it.get("modules", {})
                author = mods.get("module_author", {})
                archive = (mods.get("module_dynamic", {})
                           .get("major", {}).get("archive") or {})
                bvid = archive.get("bvid")
                name = author.get("name", "")
                created = int(author.get("pub_ts") or 0)
                if not bvid or self._is_excluded(name) or bvid in seen_bvid:
                    continue
                seen_bvid.add(bvid)
                if created < cutoff:
                    continue
                url = f"https://www.bilibili.com/video/{bvid}"
                if url in exclude_urls:
                    continue
                cover = archive.get("cover") or ""
                if cover.startswith("http://"):
                    cover = "https://" + cover[len("http://"):]
                entries.append({
                    "title": archive.get("title", ""),
                    "url": url,
                    "author": name,
                    "created": created,
                    "pic": cover,
                })
            if not data.get("has_more") or not items or (limit and len(entries) >= limit):
                break
            offset = data.get("offset")
        entries.sort(key=lambda e: e["created"], reverse=True)
        entries = entries[:limit] if limit else entries
        for i, e in enumerate(entries):
            if self.max_videos and i >= self.max_videos:
                e["hidden"] = True
        return entries


class BiliRecommendCollector(BiliCollector):
    """首页推荐流：只留「没关注 + 播放量够 + 点赞率够」的视频。

    推荐流不按时间排序（会推老视频），所以**不做时间窗口过滤**，
    跨天去重按已推 URL（bvid 固定，可直接用）。
    """

    RCMD_URL = "https://api.bilibili.com/x/web-interface/index/top/feed/rcmd"

    def __init__(self, cfg):
        super().__init__(cfg)
        r = (cfg.get("bilibili") or {}).get("recommend") or {}
        self.min_views = int(r.get("min_views", 50000))
        self.min_like_ratio = float(r.get("min_like_ratio", 0.07))
        self.limit = int(r.get("limit", 10))
        self.max_pages = int(r.get("max_pages", 8))
        self.interval = float(r.get("request_interval", 1.2))
        self.time_budget = float(r.get("time_budget", 20))

    def _rcmd_page(self, idx):
        data = self._get(self.RCMD_URL, params={
            "fresh_type": 4, "ps": 20, "fresh_idx": idx, "fresh_idx_1h": idx,
            "feed_version": "V8", "homepage_ver": 1, "brush": 0,
        })
        return (data.get("data") or {}).get("item") or []

    @staticmethod
    def _reason_text(item):
        return str(((item.get("rcmd_reason") or {}).get("content")) or "")

    def _to_entry(self, it):
        """按「未关注 + 播放量 + 点赞率 + 屏蔽词」判定单条推荐；不通过返回 None。"""
        if it.get("goto") != "av":
            return None
        bvid = it.get("bvid")
        if not bvid:
            return None
        if int(it.get("is_followed") or 0) != 0:
            return None
        stat = it.get("stat") or {}
        views, likes = int(stat.get("view") or 0), int(stat.get("like") or 0)
        if views <= self.min_views:
            return None
        ratio = likes / views if views else 0
        if ratio <= self.min_like_ratio:
            return None
        reason = self._reason_text(it)
        if "广告" in reason or "赞助" in reason:
            return None
        author = (it.get("owner") or {}).get("name", "")
        if self._is_excluded(author):
            return None
        pic = it.get("pic") or ""
        if pic.startswith("http://"):
            pic = "https://" + pic[len("http://"):]
        return {
            "title": it.get("title", ""),
            "url": f"https://www.bilibili.com/video/{bvid}",
            "author": author,
            "bvid": bvid,
            "created": int(it.get("pubdate") or 0),
            "duration": int(it.get("duration") or 0),
            "views": views,
            "likes": likes,
            "ratio": round(ratio, 4),
            "pic": pic,
        }

    def collect(self, exclude_urls=None):
        if not self.sessdata:
            raise BiliError("bilibili sessdata not configured")
        exclude_urls = set(exclude_urls or ())
        out, seen = [], set()
        deadline = time.time() + self.time_budget
        for idx in range(1, max(1, self.max_pages) + 1):
            if time.time() >= deadline:
                break
            for it in self._rcmd_page(idx):
                bvid = it.get("bvid")
                if not bvid or bvid in seen:
                    continue
                seen.add(bvid)
                url = f"https://www.bilibili.com/video/{bvid}"
                if url in exclude_urls:
                    continue
                entry = self._to_entry(it)
                if not entry:
                    continue
                out.append(entry)
                if len(out) >= self.limit:
                    return out
            if idx < self.max_pages:
                remain = deadline - time.time()
                if remain > 0:
                    time.sleep(min(self.interval, remain))
        return out