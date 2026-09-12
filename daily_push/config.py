"""Config loading (backwards-compatible re-export).

The real implementation lives in :mod:`daily_push.settings_store`, which layers
``settings.json`` (tracked policy) over ``config.json`` (gitignored secrets).
"""
import os

from .settings_store import load_config  # noqa: F401  (re-export)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(BASE_DIR, "config.json")

__all__ = ["load_config", "DEFAULT_PATH", "BASE_DIR"]
