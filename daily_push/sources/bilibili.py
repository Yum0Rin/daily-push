"""Bilibili 关注动态采集.

通过「关注动态」接口 (x/polymer/web-dynamic/v1/feed/all?type=video) 一次拉取
最近投稿的视频（标题/链接/UP名/发布时间），再按窗口过滤，无需逐个访问 UP 空间。

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
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
        })
        if self.sessdata:
            self.session.cookies.set("SESSDATA", self.sessdata, domain=".bilibili.com")
        self._img_key = None
        self._sub_key = None

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

    def collect(self):
        if not self.sessdata:
            raise BiliError("bilibili sessdata not configured")
        cutoff = datetime.datetime.combine(
            datetime.date.today() - datetime.timedelta(days=self.recent_days),
            datetime.time.min).timestamp()
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
                if not bvid or name in self.exclude or bvid in seen_bvid:
                    continue
                if created < cutoff:
                    continue
                seen_bvid.add(bvid)
                entries.append({
                    "title": archive.get("title", ""),
                    "url": f"https://www.bilibili.com/video/{bvid}",
                    "author": name,
                    "created": created,
                })
            if not data.get("has_more") or not items or len(entries) >= self.max_videos:
                break
            offset = data.get("offset")
        entries.sort(key=lambda e: e["created"], reverse=True)
        return entries[: self.max_videos]