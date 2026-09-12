"""Backfill covers for already-collected history (throttled).

- netease: rewrite stored ``pic`` to https (no request).
- bilibili: fetch the video cover via the public view API, one call per video,
  with ``interval`` sleep between calls (see AGENTS.md 控频).  Videos the API
  reports as 不存在/不可见/审核中/无权限 are **removed** from history.

Usage:
    python -m daily_push.cover_backfill [days] [interval]
"""
import re
import sys
import time

import requests

# -404 不存在 / -403 无权限 / 620xx 稿件不可见、审核中、私密等
def _is_invalid(code):
    return code in (-404, -403) or (isinstance(code, int) and 62000 <= code < 63000)


def _https(url):
    url = url or ""
    return "https://" + url[len("http://"):] if url.startswith("http://") else url


def _bvid(url):
    m = re.search(r"/video/(BV[0-9A-Za-z]+)", url or "")
    return m.group(1) if m else None


def backfill_covers(storage, cfg, days=7, interval=1.0, log=print):
    """Fill missing covers (and drop dead videos).

    netease runs for all days; bilibili only for the most recent ``days`` dates
    (0/negative = all).  Returns a stats dict.
    """
    from .backfill import promote_reserve

    bili = cfg.get("bilibili") or {}
    max_videos = int(bili.get("max_videos", 10))
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
    })
    if bili.get("sessdata"):
        session.cookies.set("SESSDATA", bili["sessdata"], domain=".bilibili.com")

    dates = storage.list_dates()  # newest first
    recent = set(dates if (not days or days <= 0) else dates[:days])

    stats = {"netease_fixed": 0, "bili_fetched": 0, "bili_removed": 0,
             "bili_failed": 0, "dates": len(dates)}
    for d in dates:
        row = storage.get(d)
        if not row:
            continue
        changed = False

        ne = row.get("netease")
        if isinstance(ne, list):
            for s in ne:
                if isinstance(s, dict) and (s.get("pic") or "").startswith("http://"):
                    s["pic"] = _https(s["pic"])
                    stats["netease_fixed"] += 1
                    changed = True

        if d in recent:
            bi = row.get("bilibili")
            if isinstance(bi, list):
                kept = []
                for it in bi:
                    if not isinstance(it, dict) or it.get("pic"):
                        kept.append(it)
                        continue
                    bvid = _bvid(it.get("url"))
                    if not bvid:
                        kept.append(it)
                        continue
                    try:
                        r = session.get("https://api.bilibili.com/x/web-interface/view",
                                        params={"bvid": bvid}, timeout=15)
                        data = r.json()
                    except Exception as e:
                        stats["bili_failed"] += 1
                        log(f"[cover] {bvid} 请求失败: {e}")
                        kept.append(it)
                        time.sleep(interval)
                        continue
                    code = data.get("code")
                    pic = (data.get("data") or {}).get("pic")
                    if code == 0 and pic:
                        it["pic"] = _https(pic)
                        stats["bili_fetched"] += 1
                        kept.append(it)
                    elif _is_invalid(code):
                        stats["bili_removed"] += 1  # 失效/私密 -> 删除
                    else:
                        stats["bili_failed"] += 1
                        kept.append(it)
                    time.sleep(interval)  # 控频

                if len(kept) != len(bi):
                    row["bilibili"] = promote_reserve(kept, max_videos)
                    changed = True

        if changed:
            storage.save(d, netease=ne, bilibili=row.get("bilibili"),
                         mp=row.get("mp"), overwrite=True)
        log(f"[cover] {d}: fetched={stats['bili_fetched']} removed={stats['bili_removed']} "
            f"failed={stats['bili_failed']} netease_fixed={stats['netease_fixed']}")
    return stats


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    import os
    from .config import load_config
    from .storage import Storage
    cfg = load_config()
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    storage = Storage(os.path.join(base, cfg.get("data_dir", "data")))
    stats = backfill_covers(storage, cfg, days=days, interval=interval)
    storage.close()
    print(f"[cover] done: {stats}")


if __name__ == "__main__":
    main()
