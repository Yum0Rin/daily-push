"""GitHub Actions 云端采集入口：只跑网易云 + B站，然后导出站点。

云端没有微信解密环境，因此不采集公众号（mp）。导出前先把已发布的站点数据
（origin/main 的 __DAYS__，含本地采集的公众号推文与历史）合并进本地库，
避免「公众号没搜到 → 覆盖已搜到记录」/ 云端清空历史。

用法：python tools/cloud_collect.py
"""
import json
import os
import re
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from daily_push.collector import collect_once  # noqa: E402
from daily_push.config import load_config  # noqa: E402
from daily_push.export_site import export_site  # noqa: E402
from daily_push.storage import Storage  # noqa: E402


def _published_days():
    """Return {push_date: {netease, bilibili, mp}} from origin/main index.html, or {}."""
    try:
        subprocess.run(
            ["git", "fetch", "-q", "origin", "main"],
            capture_output=True, timeout=60,
        )
        out = subprocess.run(
            ["git", "show", "origin/main:index.html"],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
        if out.returncode != 0:
            return {}
    except Exception:
        return {}
    html = out.stdout
    m = re.search(r"window\.__DAYS__\s*=\s*(\{.*?\})\s*;\s*</script>", html, re.S)
    if not m:
        return {}
    try:
        days = json.loads(m.group(1))
        if isinstance(days, dict):
            return days
    except Exception:
        pass
    return {}


def _seed_published(storage, days):
    """Write published days into local DB so export keeps history + local mp."""
    for d, fields in days.items():
        if not isinstance(fields, dict):
            continue
        storage.save(
            d,
            netease=fields.get("netease"),
            bilibili=fields.get("bilibili"),
            mp=fields.get("mp"),
        )


def main():
    cfg = load_config()
    data_dir = cfg.get("data_dir", "data")
    storage = Storage(os.path.join(BASE_DIR, data_dir))

    _seed_published(storage, _published_days())
    storage.close()

    r = collect_once(netease=True, bilibili=True, wechat=False)
    errs = {k: v.get("error") for k, v in r.items()
            if isinstance(v, dict) and "error" in v}
    print("collect errors:", errs)
    status = {"push_date": r.get("push_date"), "errors": errs}
    with open(os.path.join(BASE_DIR, "cloud_status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    p = export_site()
    print("exported:", p)


if __name__ == "__main__":
    main()
