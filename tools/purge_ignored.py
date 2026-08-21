"""按 config 忽略名单清除历史数据并重新发布。

用法: python tools/purge_ignored.py [--no-push]

- bilibili: 按 author 名包含 config.bilibili.exclude 中任一关键词的条目
- mp(公众号): 按 author/title 包含 config.wechat.exclude_keywords 中任一关键词的条目

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
                title = (it or {}).get("title", "")
                if any(k and (k in author or k in title) for k in mp_exclude):
                    removed["mp"].append((d, author))
                    changed = True
                else:
                    kept.append(it)
            if changed:
                row["mp"] = kept
        if changed:
            storage.save(d, netease=row.get("netease"),
                         bilibili=row.get("bilibili") or None,
                         mp=row.get("mp") or None)
    return removed


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
