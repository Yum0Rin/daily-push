"""Netease Cloud Music daily recommend collector.

Calls a local NeteaseCloudMusicApi instance (https://github.com/Binaryify/NeteaseCloudMusicApi)
running on config.netease.base_url (default http://localhost:3000).
The daily-recommend endpoints require a logged-in cookie (MUSIC_U and __csrf).
"""
import requests


class NeteaseError(Exception):
    pass


class NeteaseCollector:
    def __init__(self, cfg):
        netease = cfg.get("netease", {})
        self.base = (netease.get("base_url") or "http://localhost:3000").rstrip("/")
        self.cookie = netease.get("cookie") or ""
        self.max_songs = cfg.get("max_songs", 5)
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

    def _hot_comment(self, song_id):
        """Return top hot comment text for a song, or '' if unavailable."""
        try:
            data = self._get("/comment/music", params={"id": song_id, "limit": 1})
            hc = data.get("hotComments") or []
            if hc and hc[0].get("content"):
                return hc[0]["content"].strip()
        except Exception:
            pass
        return ""

    def top_songs(self):
        """Return top N recommended daily songs via /recommend/songs."""
        data = self._get("/recommend/songs")
        songs = (data.get("data") or {}).get("dailySongs") or []
        out = []
        for s in songs[: self.max_songs]:
            ar = " / ".join([a.get("name", "") for a in s.get("ar", [])])
            out.append({
                "id": s.get("id"),
                "name": s.get("name", ""),
                "artists": ar,
                "album": (s.get("al") or {}).get("name", ""),
                "duration_ms": s.get("dt"),
                "pic": (s.get("al") or {}).get("picUrl", ""),
                "url": f"https://music.163.com/song?id={s.get('id')}",
                "hot_comment": self._hot_comment(s.get("id")),
            })
        return out

    def collect(self):
        if not self.cookie:
            raise NeteaseError("netease cookie not configured")
        return self.top_songs()