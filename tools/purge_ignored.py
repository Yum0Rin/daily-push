"""按 config 忽略名单清除历史数据并重新发布。

用法: python tools/purge_ignored.py [--no-push]

- bilibili: 按 author 名包含 bilibili.exclude 中任一关键词的条目
- mp(公众号): 按 author（公众号名）包含 wechat.exclude_keywords 中任一关键词的条目
  （仅作者，不匹配标题，避免误伤）

从本地库所有历史日期删除后，重新导出静态站，可选推送 GitHub Pages。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from daily_push.config import load_config
from daily_push.backfill import promote_reserve
from daily_push.storage import Storage

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def purge(storage, cfg):
    bili_exclude = [str(k) for k in cfg.get("bilibili", {}).get("exclude", [])]
    mp_exclude = [str(k) for k in cfg.get("wechat", {}).get("exclude_keywords", [])]
    max_videos = int(cfg.get("bilibili", {}).get("max_videos", 10))
    max_articles = int(cfg.get("wechat", {}).get("max_articles", 10))
    removed = {"bilibili": [], "mp": []}
    for d in storage.list_dates():
        row = storage.get(d)
        if not row:
            continue
        changed = False
        if row.get("bilibili"):
            kept, hit = [], False
            for it in row["bilibili"]:
                author = (it or {}).get("author", "")
                if any(k and k in author for k in bili_exclude):
                    removed["bilibili"].append((d, author))
                    hit = True
                else:
                    kept.append(it)
            if hit:
                row["bilibili"] = promote_reserve(kept, max_videos)
                changed = True
        if row.get("mp"):
            kept, hit = [], False
            for it in row["mp"]:
                author = (it or {}).get("author", "")
                if any(k and k in author for k in mp_exclude):
                    removed["mp"].append((d, author))
                    hit = True
                else:
                    kept.append(it)
            if hit:
                row["mp"] = promote_reserve(kept, max_articles)
                changed = True
        if changed:
            storage.save(d, netease=row.get("netease"),
                         bilibili=row.get("bilibili") or None,
                         mp=row.get("mp") or None,
                         overwrite=True)
    return removed


def _build_netease_stats(cfg):
    """stats(song_id) -> (comment_count | None, favorite_count | None)."""
    try:
        from daily_push.sources.netease import NeteaseCollector
        collector = NeteaseCollector(cfg)
    except Exception:
        return None

    def stats(song_id):
        try:
            total, _ = collector._comment_info(song_id)
        except Exception:
            total = None
        try:
            fav = collector._red_count(song_id)
        except Exception:
            fav = None
        return total, fav
    return stats


def purge_and_publish(cfg=None, config_path=None, netease_stats=None):
    """Backfill counts + remove ignored/over-commented entries, then republish.

    Returns a stats dict: removal counts, backfill count, export path, push result.
    Used both by the CLI and by the local settings page.
    """
    cfg = cfg or load_config(config_path)
    data_dir = cfg.get("data_dir", "data")
    storage = Storage(os.path.join(PROJECT_DIR, data_dir))

    from daily_push.export_site import export_site, push_site, merge_remote_history
    # Merge remote-only days FIRST so purge also cleans them; otherwise the later
    # export's merge would re-introduce ignored entries and push them back.
    merge_remote_history(storage, cfg)
    removed = purge(storage, cfg)

    # netease: backfill comment/favorite counts + drop over-threshold songs
    from daily_push.netease_history import apply_history
    netease_cfg = cfg.get("netease") or {}
    max_comments = netease_cfg.get("max_comments", 10000)
    max_favorites = netease_cfg.get("max_favorites", 0)
    interval = float(netease_cfg.get("request_interval", 0.3))
    if netease_stats is None:
        netease_stats = _build_netease_stats(cfg)
    netease_result = apply_history(storage, max_comments, max_favorites,
                                   netease_stats, interval,
                                   shown_target=int(cfg.get("max_songs", 5)))
    storage.close()

    exported = export_site(config_path=config_path, merge_remote=False)  # history already merged
    pushed = None
    push_error = None
    try:
        pushed = push_site(config_path=config_path)
    except Exception as e:
        push_error = str(e)
    return {
        "removed_bilibili": len(removed["bilibili"]),
        "removed_mp": len(removed["mp"]),
        "removed_netease": len(netease_result["removed"]),
        "backfilled_netease": netease_result["backfilled"],
        "exported": exported,
        "pushed": pushed,
        "push_error": push_error,
    }


def main():
    cfg = load_config()
    data_dir = cfg.get("data_dir", "data")
    storage = Storage(os.path.join(PROJECT_DIR, data_dir))
    removed = purge(storage, cfg)
    storage.close()

    for k in ("bilibili", "mp"):
        items = removed[k]
        print(f"[{k}] removed {len(items)} entries")
        for d, author in items:
            print(f"    {d}  {author}")

    from daily_push.export_site import export_site, push_site
    path = export_site()
    print("exported:", path)
    if "--no-push" not in sys.argv:
        print("pushed:", push_site())


if __name__ == "__main__":
    main()
