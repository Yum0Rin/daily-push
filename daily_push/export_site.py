"""导出自包含静态页并推送到 GitHub Pages.

每次采集完成后生成 site/index.html（内联 CSS/JS + 全部日期数据 window.__DAYS__），
再用 git push 到配置的 GitHub 仓库，手机即可访问 Pages 链接（电脑可关机）。
"""
import json
import os
import re
import subprocess

from .config import load_config
from .storage import Storage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)


def _site_dir(cfg):
    return os.path.join(PROJECT_DIR, cfg.get("site", {}).get("export_dir", "site"))


def _published_days_from_remote(cfg):
    """Return {push_date: {netease, bilibili, mp}} from the published site on GitHub,
    or {} if unavailable.  This preserves historical days that are not in the local DB
    (e.g. a fresh machine) so a local export/push never erases previously published data.
    """
    site_cfg = cfg.get("site") or {}
    repo = str(site_cfg.get("repo") or "").strip()
    branch = str(site_cfg.get("branch") or "main")
    if not repo:
        return {}
    try:
        remote = f"https://github.com/{repo}.git"
        subprocess.run(["git", "fetch", "-q", "origin", "main"],
                       cwd=PROJECT_DIR, capture_output=True, timeout=60)
        out = subprocess.run(["git", "show", f"origin/{branch}:index.html"],
                             cwd=PROJECT_DIR, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60)
        if out.returncode != 0:
            return {}
        m = re.search(r"window\.__DAYS__\s*=\s*(\{.*?\})\s*;\s*</script>",
                      out.stdout, re.S)
        if not m:
            return {}
        days = json.loads(m.group(1))
        return days if isinstance(days, dict) else {}
    except Exception:
        return {}


def _merge_published(storage, days):
    """Write published days into local DB so export keeps full history.

    只补「本地缺失的日期」，不覆盖本地已有的（本地可能更全，如本地采集的 mp）。
    """
    for d, fields in days.items():
        if storage.has(d):
            continue
        if not isinstance(fields, dict):
            continue
        storage.save(d, netease=fields.get("netease"),
                     bilibili=fields.get("bilibili"), mp=fields.get("mp"))


def export_site(config_path=None, merge_remote=True):
    """Build a self-contained site/index.html with all stored days inlined.

    If merge_remote is True (default), published days are merged from the GitHub
    site first so the export always contains the full history.
    """
    cfg = load_config(config_path)
    data_dir = cfg.get("data_dir", "data")
    storage = Storage(os.path.join(PROJECT_DIR, data_dir))
    if merge_remote:
        _merge_published(storage, _published_days_from_remote(cfg))
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
    """Update only index.html on the configured GitHub repo (Pages) branch.

    Uses a worktree pinned to the existing remote branch so other files on the
    branch (e.g. .github/workflows) are preserved instead of being wiped out by
    a force push of a fresh single-file repo.
    """
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
        r = subprocess.run(args, cwd=site, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0 and not ok_fail:
            raise RuntimeError(f"{' '.join(args)} -> {r.stderr[:200]}")
        return r

    index_html = os.path.join(site, "index.html")
    if not os.path.exists(index_html):
        raise RuntimeError("site/index.html not found; run export_site() first")

    # Keep a copy of the freshly exported index.html (reset will overwrite it).
    with open(index_html, "rb") as f:
        exported = f.read()

    # Init a repo that is tied to the real remote branch.
    run(["git", "init", "-q"])
    run(["git", "remote", "remove", "origin"], ok_fail=True)
    run(["git", "remote", "add", "origin", remote])
    run(["git", "branch", "-M", branch])
    run(["git", "fetch", "-q", "origin", branch], ok_fail=True)
    # Reset working tree to the remote branch (preserves other files like the workflow).
    if run(["git", "rev-parse", "-q", "--verify", f"origin/{branch}"], ok_fail=True).returncode == 0:
        run(["git", "reset", "-q", "--hard", f"origin/{branch}"])
    # Restore the freshly exported index.html.
    with open(index_html, "wb") as f:
        f.write(exported)
    # Stage/commit only index.html so the branch keeps its other content.
    run(["git", "add", "index.html"])
    run(["git", "commit", "-q", "--allow-empty", "-m", "daily push"])
    run(["git", "push", "-q", "origin", branch])
    return remote
