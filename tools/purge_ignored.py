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
from daily_push.storage import Storage

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def purge(storage, cfg):
    bili_exclude = [str(k) for k in cfg.get("bilibili", {}).get("exclude", [])]
    mp_exclude = [str(k) for k in cfg.get("wechat", {}).get("exclude_keywords", [])]
    removed = {"bilibili": [], "mp": []}
    for d in storage.list_dates():
        row = storage.get(d)
        if not row:
            continue
        changed = False
        if row.get("bilibili"):
            kept = []
            for it in row["bilibili"]:
                author = (it or {}).get("author", "")
                if any(k and k in author for k in bili_exclude):
                    removed["bilibili"].append((d, author))
                    changed = True
                else:
                    kept.append(it)
            if changed:
                row["bilibili"] = kept
        if row.get("mp"):
            kept = []
            for it in row["mp"]:
                author = (it or {}).get("author", "")
                if any(k and k in author for k in mp_exclude):
                    removed["mp"].append((d, author))
                    changed = True
                else:
                    kept.append(it)
            if changed:
                row["mp"] = kept
        if changed:
            storage.save(d, netease=row.get("netease"),
                         bilibili=row.get("bilibili") or None,
                         mp=row.get("mp") or None,
                         overwrite=True)
    return removed


def purge_and_publish(cfg=None, config_path=None):
    """Remove ignored entries from ALL history/today, re-export and push Pages.

    Returns a stats dict: removal counts, export path, push result/error.
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
