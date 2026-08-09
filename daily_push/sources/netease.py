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

import requests


class NeteaseError(Exception):
    pass


class _NeteaseHttp:
    """Legacy backend: local NeteaseCloudMusicApi proxy + cookie."""

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

    def collect(self):
        if not self.cookie:
            raise NeteaseError("netease cookie not configured")
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


class _NeteaseNcmCli:
    """Official backend: drive the `ncm-cli` command line tool."""

    CMD = "ncm-cli"

    def __init__(self, cfg):
        self.max_songs = cfg.get("max_songs", 5)
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
        if r.returncode != 0:
            msg = (r.stderr or r.stdout or "").strip()
            if "请先登录" in msg or "未登录" in msg or "login" in msg.lower():
                raise NeteaseError("ncm-cli 未登录，请先执行 ncm-cli login")
            if "API key" in msg or "appId" in msg:
                raise NeteaseError("ncm-cli API key 未配置，请执行 ncm-cli configure")
            raise NeteaseError(f"ncm-cli failed: {msg[:200]}")
        try:
            return json.loads(r.stdout)
        except ValueError:
            raise NeteaseError("ncm-cli returned non-JSON output")

    def _daily_songs(self):
        data = self._cli("recommend", "daily", "--limit", str(self.max_songs))
        return data.get("data") or []

    def _hot_comment(self, enc_id):
        """Top hot comment via official comment API; '' if unavailable."""
        try:
            data = self._cli("comment", "list-hot", "--type", "song",
                             "--resourceId", str(enc_id),
                             "--limit", "1", "--offset", "0")
            records = (data.get("data") or {}).get("records") or []
            if records and records[0].get("content"):
                return records[0]["content"].strip()
        except Exception:
            pass
        return ""

    def collect(self):
        songs = self._daily_songs()
        if not songs:
            raise NeteaseError("ncm-cli returned no daily songs")
        out = []
        for s in songs[: self.max_songs]:
            ar = " / ".join([a.get("name", "") for a in (s.get("artists") or [])])
            out.append({
                "id": s.get("originalId"),
                "name": s.get("name", ""),
                "artists": ar,
                "album": (s.get("album") or {}).get("name", ""),
                "duration_ms": s.get("duration"),
                "pic": s.get("coverImgUrl", ""),
                "url": f"https://music.163.com/song?id={s.get('originalId')}",
                "hot_comment": self._hot_comment(s.get("id")),
            })
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
