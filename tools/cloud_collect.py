"""GitHub Actions 云端采集入口：只跑网易云 + B站，然后导出站点。

用法：python tools/cloud_collect.py
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from daily_push.collector import collect_once  # noqa: E402
from daily_push.export_site import export_site  # noqa: E402


def main():
    r = collect_once(netease=True, bilibili=True)
    errs = {k: v.get("error") for k, v in r.items()
            if isinstance(v, dict) and "error" in v}
    print("collect errors:", errs)
    p = export_site()
    print("exported:", p)


if __name__ == "__main__":
    main()
