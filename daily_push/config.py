"""Config loading."""
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(BASE_DIR, "config.json")


def load_config(path=None):
    path = path or DEFAULT_PATH
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("netease", {})
    cfg["netease"].setdefault("mode", "ncm-cli")
    cfg.setdefault("bilibili", {})
    cfg["bilibili"].setdefault("up_ids", [])
    cfg.setdefault("qq", {})
    cfg["qq"].setdefault("accounts", [])
    cfg["qq"].setdefault("important_groups", [])
    cfg["qq"].setdefault("top_groups", 3)
    cfg["qq"].setdefault("max_per_group", 5)
    cfg.setdefault("wechat", {})
    cfg["wechat"].setdefault("important_groups", [])
    cfg["wechat"].setdefault("top_groups", 3)
    cfg["wechat"].setdefault("max_per_group", 5)
    cfg.setdefault("max_songs", 5)
    cfg.setdefault("data_dir", "data")
    return cfg