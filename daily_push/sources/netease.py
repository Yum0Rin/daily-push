"""Netease Cloud Music daily recommend collector.

Two interchangeable backends, selected by ``netease.mode`` in config:

- ``api`` (default): legacy unofficial path through a local NeteaseCloudMusicApi instance
  (https://github.com/Binaryify/NeteaseCloudMusicApi) on ``netease.base_url``,
  using a logged-in cookie.
- ``ncm-cli`` (backup): official openapi via the `ncm-cli` command line tool.
  Requires `ncm-cli` installed and logged in on this machine
  (``ncm-cli login`` once). No cookie / no local Node proxy needed.

Both backends emit the same list-of-dicts shape:
  [{id, name, artists, album, duration_ms, pic, url, hot_comment}, ...]
"""
import json
import shutil
import subprocess
import time

import requests

DEFAULT_REQUEST_INTERVAL = 0.3  # seconds between netease API calls (be gentle)


class NeteaseError(Exception):
    pass


class _NeteaseHttp:
    """Legacy backend: local NeteaseCloudMusicApi proxy + cookie."""

    def __init__(self, cfg):
        netease = cfg.get("netease", {})
        self.base = (netease.get("base_url") or "http://localhost:3000").rstrip("/")
        self.cookie = netease.get("cookie") or ""
        self.max_songs = cfg.get("max_songs", 5)
        self.max_comments = netease.get("max_comments", 10000)
        self.max_favorites = netease.get("max_favorites", 0)
        self.reserve = int(netease.get("reserve", 3))
        self.request_interval = float(netease.get("request_interval", DEFAULT_REQUEST_INTERVAL))
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://music.163.com/",
        })

    def _get(self, path, params=None):
        url = self.base + path
        headers = {"Cookie": self.cookie} if self.cookie else {}
        try:
            r = self.session.get(url, params=params or {}, headers=headers, timeout=20)
        except requests.exceptions.RequestException as e:
            raise NeteaseError(f"cannot reach NeteaseCloudMusicApi: {e}")
        if r.status_code != 200:
            raise NeteaseError(f"api returned {r.status_code}")
        try:
            data = r.json()
        except ValueError:
            raise NeteaseError("api returned non-JSON")
        if data.get("code") not in (0, 200):
            raise NeteaseError(f"api error {data.get('code')}: {data.get('msg')}")
        return data

    def _comment_info(self, song_id):
        """Return (total_comments or None, top hot comment text).

        One call to ``/comment/music`` yields both the total count and the top
        hot comment, so filtering by popularity costs nothing extra.
        """
        try:
            data = self._get("/comment/music", params={"id": song_id, "limit": 1})
            total = data.get("total")
            hc = data.get("hotComments") or []
            hot = hc[0]["content"].strip() if hc and hc[0].get("content") else ""
            return (int(total) if total is not None else None), hot
        except Exception:
            return None, ""

    def _red_count(self, song_id):
        """Return the song's red-heart (收藏/喜欢) count, or None."""
        try:
            data = self._get("/song/red/count", params={"id": song_id})
            count = (data.get("data") or {}).get("count")
            return int(count) if count is not None else None
        except Exception:
            return None

    def collect(self):
        if not self.cookie:
            raise NeteaseError("netease cookie not configured")
        data = self._get("/recommend/songs")
        songs = (data.get("data") or {}).get("dailySongs") or []
        out = []
        reserve = max(0, self.reserve) if self.max_songs else 0
        limit = (self.max_songs + reserve) if self.max_songs else 0  # 0=不限
        for s in songs:
            if limit and len(out) >= limit:
                break
            total, hot = self._comment_info(s.get("id"))
            if self.request_interval:
                time.sleep(self.request_interval)
            # 评论过多的“大众歌”跳过，顺延下一首（max_comments=0 表示不限）
            if self.max_comments and total is not None and total > self.max_comments:
                continue
            fav = self._red_count(s.get("id"))
            if self.request_interval:
                time.sleep(self.request_interval)
            # 收藏过多的歌同样跳过（max_favorites=0 表示不限）
            if self.max_favorites and fav is not None and fav > self.max_favorites:
                continue
            ar = " / ".join([a.get("name", "") for a in s.get("ar", [])])
            pic = (s.get("al") or {}).get("picUrl", "") or ""
            if pic.startswith("http://"):  # 避免 http 图片被 https 页面/ CSP 拦截
                pic = "https://" + pic[len("http://"):]
            out.append({
                "id": s.get("id"),
                "name": s.get("name", ""),
                "artists": ar,
                "album": (s.get("al") or {}).get("name", ""),
                "duration_ms": s.get("dt"),
                "pic": pic,
                "url": f"https://music.163.com/song?id={s.get('id')}",
                "hot_comment": hot,
                "comment_count": total,
                "favorite_count": fav,
            })
        for i, item in enumerate(out):
            if self.max_songs and i >= self.max_songs:
                item["hidden"] = True
        return out


class _NeteaseNcmCli:
    """Official backend: drive the `ncm-cli` command line tool."""

    CMD = "ncm-cli"

    def __init__(self, cfg):
        self.max_songs = cfg.get("max_songs", 5)
        self.max_comments = (cfg.get("netease") or {}).get("max_comments", 10000)
        self.reserve = int((cfg.get("netease") or {}).get("reserve", 3))
        if shutil.which(self.CMD) is None:
            raise NeteaseError("ncm-cli not found in PATH; install it with "
                               "'npm install -g @music163/ncm-cli'")

    def _cli(self, *args):
        """Run ncm-cli and parse its JSON output."""
        try:
            r = subprocess.run(
                [self.CMD, *args],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", shell=True, timeout=60,
            )
        except subprocess.TimeoutExpired:
            raise NeteaseError("ncm-cli timed out")
        combined = (r.stderr or "") + (r.stdout or "")
        if r.returncode != 0:
            msg = (r.stderr or r.stdout or "").strip()
            if "请先登录" in msg or "未登录" in msg or "login" in msg.lower():
                raise NeteaseError("ncm-cli 登录态失效，请手动执行 ncm-cli login"
                                   "（邮件自动补 Cookie 仅适用于 api 模式，ncm-cli 需手动登录）")
            if "API key" in msg or "appId" in msg:
                raise NeteaseError("ncm-cli API key 未配置，请执行 ncm-cli configure")
            raise NeteaseError(f"ncm-cli failed: {msg[:200]}")
        # 断网规则：ncm-cli 远端同步失败时会「使用本地缓存」返回过期数据，
        # 这里检测到缓存回退即当作硬错误，绝不用昨天的推荐冒充当天数据。
        if any(k in combined for k in ("远端同步失败", "使用本地缓存", "本地缓存")):
            raise NeteaseError("ncm-cli 远端同步失败（网络异常），拒绝使用本地缓存，"
                               "请检查网络后重试")
        try:
            return json.loads(r.stdout)
        except ValueError:
            raise NeteaseError("ncm-cli returned non-JSON output")

    def _daily_songs(self):
        data = self._cli("recommend", "daily", "--limit", str(self.max_songs))
        return data.get("data") or []

    def _comment_info(self, enc_id):
        """Best-effort (total_comments or None, top hot comment) via ncm-cli."""
        try:
            data = self._cli("comment", "list-hot", "--type", "song",
                             "--resourceId", str(enc_id),
                             "--limit", "1", "--offset", "0")
            records = (data.get("data") or {}).get("records") or []
            total = data.get("total")
            if total is None:
                total = (data.get("data") or {}).get("total")
            hot = records[0]["content"].strip() if records and records[0].get("content") else ""
            return (int(total) if total is not None else None), hot
        except Exception:
            return None, ""

    def collect(self):
        songs = self._daily_songs()
        if not songs:
            raise NeteaseError("ncm-cli returned no daily songs")
        out = []
        reserve = max(0, self.reserve) if self.max_songs else 0
        limit = (self.max_songs + reserve) if self.max_songs else 0  # 0=不限
        for s in songs:
            if limit and len(out) >= limit:
                break
            total, hot = self._comment_info(s.get("id"))
            if self.max_comments and total is not None and total > self.max_comments:
                continue
            ar = " / ".join([a.get("name", "") for a in (s.get("artists") or [])])
            pic = s.get("coverImgUrl", "") or ""
            if pic.startswith("http://"):
                pic = "https://" + pic[len("http://"):]
            out.append({
                "id": s.get("originalId"),
                "name": s.get("name", ""),
                "artists": ar,
                "album": (s.get("album") or {}).get("name", ""),
                "duration_ms": s.get("duration"),
                "pic": pic,
                "url": f"https://music.163.com/song?id={s.get('originalId')}",
                "hot_comment": hot,
                "comment_count": total,
                "favorite_count": None,
            })
        for i, item in enumerate(out):
            if self.max_songs and i >= self.max_songs:
                item["hidden"] = True
        return out


def NeteaseCollector(cfg):
    """Factory: pick the netease backend from config netease.mode.

    mode ``api`` uses the legacy NeteaseCloudMusicApi proxy (default);
    mode ``ncm-cli`` uses the official CLI (backup).
    """
    mode = (cfg.get("netease") or {}).get("mode", "api")
    if mode == "api":
        return _NeteaseHttp(cfg)
    return _NeteaseNcmCli(cfg)
