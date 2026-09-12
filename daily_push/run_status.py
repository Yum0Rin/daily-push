"""Tiny run-status tracker for the settings page.

Records the last successful collect / push / credential check into
``<data_dir>/status.json`` so the UI can show "上次…" timestamps without
re-querying anything.
"""
import json
import os
from datetime import datetime

from .config import load_config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _path():
    try:
        data_dir = load_config().get("data_dir", "data")
    except Exception:
        data_dir = "data"
    return os.path.join(BASE_DIR, data_dir, "status.json")


def read():
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def record(key, detail=None):
    """Mark ``key`` as happening now, optionally with a short detail string."""
    path = _path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = read()
        data[key] = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "detail": detail or "",
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
