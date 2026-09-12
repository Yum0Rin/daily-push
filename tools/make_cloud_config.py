"""在 GitHub Actions 云端根据环境变量生成 config.json。

用法：
    NETEASE_COOKIE=... BILIBILI_SESSDATA=... python tools/make_cloud_config.py

策略（屏蔽名单 / 阈值 / push_time）来自仓库内跟踪的 ``settings.json``，
与本地完全同源；只有凭证从 Secrets 注入。公众号/QQ 云端不采集。
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _deep_merge(base, patch):
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


with open(os.path.join(BASE_DIR, "config.example.json"), encoding="utf-8") as f:
    cfg = json.load(f)

settings_path = os.path.join(BASE_DIR, "settings.json")
if os.path.exists(settings_path):
    with open(settings_path, encoding="utf-8") as f:
        _deep_merge(cfg, json.load(f))

cfg["netease"]["cookie"] = os.environ.get("NETEASE_COOKIE", "")
cfg["netease"]["base_url"] = "http://localhost:3000"
cfg["bilibili"]["sessdata"] = os.environ.get("BILIBILI_SESSDATA", "")

out = os.path.join(BASE_DIR, "config.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
print(f"wrote {out}")
