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


def backfill_wechat_covers(storage, cfg, since_days=180, log=print):
    """Backfill covers on stored 公众号 articles from the local WeChat DB (no network).

    Articles without a cover are kept (non-standard messages still get pushed);
    the frontend renders a placeholder for them.
    """
    from .sources.wechat_article import WeChatArticleCollector
    since = int(time.time()) - max(0, since_days) * 86400
    cmap = WeChatArticleCollector(cfg).cover_map(since_ts=since)
    if not cmap:
        log("[cover] wechat: 未扫描到封面，跳过")
        return {"wechat_fixed": 0, "wechat_covers": 0}

    fixed = 0
    for d in storage.list_dates():
        row = storage.get(d)
        mp = (row or {}).get("mp")
        if not isinstance(mp, list):
            continue
        changed = False
        for a in mp:
            if isinstance(a, dict) and not a.get("pic") and a.get("url") in cmap:
                a["pic"] = cmap[a["url"]]
                fixed += 1
                changed = True
        if changed:
            storage.save(d, netease=row.get("netease"), bilibili=row.get("bilibili"),
                         mp=mp, overwrite=True)
    log(f"[cover] wechat: fixed={fixed} covers={len(cmap)}")
    return {"wechat_fixed": fixed, "wechat_covers": len(cmap)}


def backfill_wechat_history(storage, cfg, since_days=180, log=print):
    """Fill each day's 公众号 list up to ``max_articles`` from the local WeChat DB."""
    import datetime
    from .sources.wechat_article import WeChatArticleCollector
    max_articles = int((cfg.get("wechat") or {}).get("max_articles", 12))
    since = int(time.time()) - max(0, since_days) * 86400
    arts = WeChatArticleCollector(cfg).scan_all(since_ts=since)
    if not arts:
        log("[fill] wechat history: 无数据，跳过")
        return {"wechat_filled": 0}
    tz = datetime.timezone(datetime.timedelta(hours=8))
    by_date = {}
    for a in arts:
        d = datetime.datetime.fromtimestamp(a["timestamp"], tz).date().isoformat()
        by_date.setdefault(d, []).append(a)

    filled = 0
    for d in storage.list_dates():
        row = storage.get(d)
        if not row:
            continue
        existing = row.get("mp") or []
        seen = {a.get("url") for a in existing if isinstance(a, dict)}
        extra = [a for a in by_date.get(d, []) if a["url"] not in seen]
        if not extra:
            continue
        merged = list(existing) + extra
        merged.sort(key=lambda x: (x.get("notify", False), -x["timestamp"]))
        if max_articles:
            merged = merged[:max_articles]
        if len(merged) > len(existing):
            filled += len(merged) - len(existing)
            storage.save(d, netease=row.get("netease"), bilibili=row.get("bilibili"),
                         mp=merged, overwrite=True)
    log(f"[fill] wechat history: filled={filled}")
    return {"wechat_filled": filled}


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
    try:
        stats.update(backfill_wechat_covers(storage, cfg))
        stats.update(backfill_wechat_history(storage, cfg))
    except Exception as e:
        print(f"[cover/fill] wechat skipped: {e}")
    storage.close()
    print(f"[cover] done: {stats}")


if __name__ == "__main__":
    main()
