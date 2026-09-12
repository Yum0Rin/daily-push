"""Layered settings persistence for daily-push.

Two files, two trust levels:

- ``settings.json``  (tracked in git, NON-secret): cross-environment policy
  shared by local runs and GitHub Actions (ignore lists, thresholds, push time).
- ``config.json``    (gitignored, SECRET): credentials + machine-specific values
  (cookies, SMTP password, Pages repo, port, data dir).

``load_config()`` merges them as ``defaults < settings.json < config.json``:
policy edits win over a stale ``config.json`` while credentials still come only
from ``config.json``.  Secret-looking keys found in ``settings.json`` are ignored
so a policy file can never smuggle credentials.

Writes are validated against an explicit schema, merged (unknown keys preserved),
and applied atomically (temp file + ``os.replace``) with a ``.bak`` backup.
"""
import json
import os
import re
import shutil
import tempfile
import threading
from copy import deepcopy

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")

_LOCK = threading.RLock()


class SettingsError(ValueError):
    """Raised when an update does not match the editable schema."""


# --------------------------------------------------------------------------- #
# validators
# --------------------------------------------------------------------------- #
def _str(value, path):
    if not isinstance(value, str):
        raise SettingsError(f"{path} 必须是字符串")
    return value.strip()


def _secret(value, path):
    return _str(value, path)


def _int(lo, hi):
    def check(value, path):
        if isinstance(value, bool) or not isinstance(value, int):
            raise SettingsError(f"{path} 必须是整数")
        if not (lo <= value <= hi):
            raise SettingsError(f"{path} 需在 {lo}~{hi} 之间")
        return value
    return check


def _str_list(value, path):
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise SettingsError(f"{path} 必须是字符串数组")
    seen, out = set(), []
    for x in value:
        x = x.strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _hhmm(value, path):
    v = _str(value, path)
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", v)
    if not m:
        raise SettingsError(f"{path} 需为 HH:MM（如 07:30）")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def _enum(options):
    def check(value, path):
        if value not in options:
            raise SettingsError(f"{path} 只能是 {sorted(options)}")
        return value
    return check


# --------------------------------------------------------------------------- #
# schema
# --------------------------------------------------------------------------- #
# Editable policy -> written to settings.json (tracked, shared with cloud).
POLICY_SPEC = {
    "push_time": _hhmm,
    "max_songs": _int(1, 50),
    "bilibili": {
        "exclude": _str_list,
        "recent_days": _int(1, 30),
        "max_videos": _int(1, 100),
        "feed_pages": _int(1, 10),
    },
    "wechat": {
        "exclude_keywords": _str_list,
        "notify_keywords": _str_list,
        "important_biz": _str_list,
        "max_articles": _int(1, 100),
        "mp_cutoff_hour": _int(0, 23),
    },
}

# Editable credentials / machine settings -> written to config.json (gitignored).
SECRET_SPEC = {
    "netease": {
        "mode": _enum({"api", "ncm-cli"}),
        "cookie": _secret,
        "base_url": _str,
    },
    "bilibili": {"sessdata": _secret},
    "email": {
        "smtp_host": _str,
        "smtp_port": _int(1, 65535),
        "smtp_user": _str,
        "smtp_pass": _secret,
        "mail_to": _str,
        "imap_host": _str,
        "imap_port": _int(1, 65535),
    },
    "site": {"repo": _str, "branch": _str, "export_dir": _str},
    "xiaohongshu": {"cookie": _secret, "limit": _int(1, 100)},
    "port": _int(1, 65535),
    "data_dir": _str,
}

_SECRET_ROOTS = {"email", "site", "port", "data_dir", "xiaohongshu"}
_SECRET_LEAVES = {
    ("netease", "cookie"),
    ("netease", "mode"),
    ("netease", "base_url"),
    ("bilibili", "sessdata"),
}


# --------------------------------------------------------------------------- #
# io helpers
# --------------------------------------------------------------------------- #
def _read_json(path, default=None):
    if not os.path.exists(path):
        if default is None:
            raise FileNotFoundError(f"Config not found: {path}")
        return deepcopy(default)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_json(path, obj):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _backup(path):
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")


def _deep_merge(base, patch):
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def _strip_secrets(policy):
    """Remove any credential-shaped key from a policy document."""
    if not isinstance(policy, dict):
        return {}
    p = deepcopy(policy)
    for root in _SECRET_ROOTS:
        p.pop(root, None)
    for parent, leaf in _SECRET_LEAVES:
        node = p.get(parent)
        if isinstance(node, dict):
            node.pop(leaf, None)
            if not node:
                p.pop(parent, None)
    return p


def _validate(spec, data, prefix=""):
    if not isinstance(data, dict):
        raise SettingsError(f"{prefix or 'root'} 必须是对象")
    out = {}
    for k, v in data.items():
        path = f"{prefix}{k}"
        if k not in spec:
            raise SettingsError(f"未知设置项：{path}")
        rule = spec[k]
        if isinstance(rule, dict):
            out[k] = _validate(rule, v, path + ".")
        else:
            out[k] = rule(v, path)
    return out


# --------------------------------------------------------------------------- #
# load
# --------------------------------------------------------------------------- #
def _apply_defaults(cfg):
    cfg.setdefault("netease", {})
    cfg["netease"].setdefault("mode", "api")
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


def load_config(path=None, settings_path=None):
    """Return the merged, defaulted configuration dict.

    ``config.json`` provides the base (credentials, machine settings);
    ``settings.json`` policy keys override stale copies left in ``config.json``.
    """
    config_path = path or CONFIG_PATH
    settings_path = settings_path or SETTINGS_PATH
    cfg = _read_json(config_path)  # raises FileNotFoundError when absent
    policy = _strip_secrets(_read_json(settings_path, default={}))
    _deep_merge(cfg, policy)
    return _apply_defaults(cfg)


# --------------------------------------------------------------------------- #
# save
# --------------------------------------------------------------------------- #
def save_policy(updates, settings_path=None):
    """Validate + merge ``updates`` into settings.json (atomic)."""
    target = settings_path or SETTINGS_PATH
    validated = _validate(POLICY_SPEC, updates or {})
    with _LOCK:
        current = _read_json(target, default={})
        _deep_merge(current, validated)
        _atomic_write_json(target, current)
    return current


def save_secrets(updates, config_path=None):
    """Validate + merge ``updates`` into config.json (atomic, with .bak)."""
    target = config_path or CONFIG_PATH
    validated = _validate(SECRET_SPEC, updates or {})
    with _LOCK:
        current = _read_json(target, default={})
        if os.path.exists(target):
            _backup(target)
        _deep_merge(current, validated)
        _atomic_write_json(target, current)
    return current


# --------------------------------------------------------------------------- #
# views (never expose raw secrets)
# --------------------------------------------------------------------------- #
def mask(value):
    if not value:
        return ""
    s = str(value)
    if len(s) <= 8:
        return "•" * len(s)
    return f"{s[:4]}{'•' * 6}{s[-4:]}"


def policy_view(settings_path=None):
    return _read_json(settings_path or SETTINGS_PATH, default={})


def secrets_view(config_path=None):
    path = config_path or CONFIG_PATH
    cfg = _read_json(path, default={}) if os.path.exists(path) else {}
    netease = cfg.get("netease") or {}
    bilibili = cfg.get("bilibili") or {}
    email = cfg.get("email") or {}
    site = cfg.get("site") or {}
    cookie = netease.get("cookie") or ""
    sessdata = bilibili.get("sessdata") or ""
    return {
        "netease": {
            "mode": netease.get("mode") or "api",
            "base_url": netease.get("base_url") or "http://localhost:3000",
            "cookie_configured": bool(cookie),
            "cookie_masked": mask(cookie),
        },
        "bilibili": {
            "sessdata_configured": bool(sessdata),
            "sessdata_masked": mask(sessdata),
        },
        "email_configured": bool(email.get("smtp_user") and email.get("smtp_pass")),
        "site_repo": site.get("repo") or "",
    }
