"""导出自包含静态页并推送到 GitHub Pages.

每次采集完成后生成 site/index.html（内联 CSS/JS + 全部日期数据 window.__DAYS__），
再用 git push 到配置的 GitHub 仓库，手机即可访问 Pages 链接（电脑可关机）。
"""
import json
import os
import subprocess

from .config import load_config
from .storage import Storage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)


def _site_dir(cfg):
    return os.path.join(PROJECT_DIR, cfg.get("site", {}).get("export_dir", "site"))


def export_site(config_path=None):
    """Build a self-contained site/index.html with all stored days inlined."""
    cfg = load_config(config_path)
    data_dir = cfg.get("data_dir", "data")
    storage = Storage(os.path.join(PROJECT_DIR, data_dir))
    days = {}
    for d in storage.list_dates():
        row = storage.get(d)
        if row:
            days[d] = {k: row.get(k) for k in ("netease", "bilibili", "mp")}
    storage.close()

    with open(os.path.join(BASE_DIR, "templates", "index.html"), encoding="utf-8") as f:
        tpl = f.read()
    with open(os.path.join(BASE_DIR, "static", "style.css"), encoding="utf-8") as f:
        css = f.read()
    with open(os.path.join(BASE_DIR, "static", "app.js"), encoding="utf-8") as f:
        js = f.read()

    html = tpl.replace(
        '<link rel="stylesheet" href="/static/style.css">',
        f"<style>\n{css}\n</style>",
    ).replace(
        '<script src="/static/app.js"></script>',
        f'<script>window.__DAYS__ = {json.dumps(days, ensure_ascii=False)};</script>\n'
        f"<script>\n{js}\n</script>",
    )

    site = _site_dir(cfg)
    os.makedirs(site, exist_ok=True)
    path = os.path.join(site, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def push_site(config_path=None):
    """git init/add/commit/push the site dir to the configured GitHub repo."""
    cfg = load_config(config_path)
    site_cfg = cfg.get("site") or {}
    repo = str(site_cfg.get("repo") or "").strip()
    if not repo:
        return None
    branch = str(site_cfg.get("branch") or "main")
    site = _site_dir(cfg)
    os.makedirs(site, exist_ok=True)
    remote = f"https://github.com/{repo}.git"

    def run(args, ok_fail=False):
        r = subprocess.run(args, cwd=site, capture_output=True, text=True)
        if r.returncode != 0 and not ok_fail:
            raise RuntimeError(f"{' '.join(args)} -> {r.stderr[:200]}")
        return r

    run(["git", "init", "-q"])
    run(["git", "remote", "remove", "origin"], ok_fail=True)
    run(["git", "remote", "add", "origin", remote])
    run(["git", "branch", "-M", branch])
    run(["git", "add", "-A"])
    run(["git", "commit", "-q", "--allow-empty", "-m", "daily push"])
    run(["git", "push", "-q", "-f", "origin", branch])
    return remote
