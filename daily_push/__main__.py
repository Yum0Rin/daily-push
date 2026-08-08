"""CLI 入口: python -m daily_push.collect 手动触发一次采集."""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from daily_push.collector import collect_once  # noqa


def main():
    netease = "--no-netease" not in sys.argv
    bilibili = "--no-bilibili" not in sys.argv
    wechat = "--no-wechat" not in sys.argv
    result = collect_once(netease=netease, bilibili=bilibili, wechat=wechat)
    print("=" * 40)
    print("saved push_date:", result.get("push_date"))
    for k in ("netease", "bilibili", "mp"):
        if k in result:
            item = result[k]
            if isinstance(item, dict) and "error" in item:
                print(f"[{k}] ERROR: {item['error']}")
            else:
                print(f"[{k}] OK ({len(item)} items)")
        else:
            print(f"[{k}] skipped/timedout")
    print("=" * 40)


if __name__ == "__main__":
    main()