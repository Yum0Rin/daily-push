"""在 GitHub Actions 云端根据环境变量生成 config.json（cookie 来自 Secrets）。

用法：
    NETEASE_COOKIE=... BILIBILI_SESSDATA=... python tools/make_cloud_config.py

只生成云端需要的字段；公众号/QQ 在云端不采集，留空即可。
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(BASE_DIR, "config.example.json"), encoding="utf-8") as f:
    cfg = json.load(f)

cfg["netease"]["cookie"] = os.environ.get("NETEASE_COOKIE", "")
cfg["netease"]["base_url"] = "http://localhost:3000"
cfg["bilibili"]["sessdata"] = os.environ.get("BILIBILI_SESSDATA", "")
cfg["bilibili"]["exclude"] = ["冷水先森无人声助眠", "吉伊卡哇动画官方", "陶阿狗君",
                              "钢铁猛懒懒", "医学老师刘忠保", "哔哩哔哩课堂", "独自做面包"]

out = os.path.join(BASE_DIR, "config.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
print(f"wrote {out}")
