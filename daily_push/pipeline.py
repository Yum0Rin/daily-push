"""Daily pipeline: netease proxy lifecycle + one collect→export→push pass.

The NeteaseCloudMusicApi proxy (:3000) is started **lazily** — only while a
netease-touching operation runs (verify / manual push / purge / logon collect) —
then stopped again, so nothing is left running when idle.

Proxy use is reference-counted (`acquire`/`release`) so concurrent operations
share one proxy and it is only stopped when the last user is done.

Shared by:
- ``start.py`` (daemon mode, manual ``python start.py``),
- ``tools/run_daily.py`` (Windows logon one-shot),
- ``daily_push/app.py`` (settings page 检测 / 手动推送 / 清理发布).
"""
import os
import socket
import subprocess
import threading
import time

from . import proc
from . import run_status

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE_SERVER_JS = os.path.join(PROJECT_DIR, "netease_server.js")

_lock = threading.Lock()
_proxy = None   # the NeteaseCloudMusicApi Popen *we* started (None otherwise)
_refs = 0       # number of operations currently using the proxy


def _port_open(host, port, timeout=1.0):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def _netease_addr(cfg):
    base = (cfg.get("netease") or {}).get("base_url", "http://localhost:3000")
    _, _, rest = base.partition("://")
    host, _, port = rest.partition(":")
    return host or "localhost", int(port or 3000)


def _ensure_locked(wait):
    """Spawn the proxy if needed. Caller must hold ``_lock``."""
    global _proxy
    from .config import load_config
    cfg = load_config()
    if (cfg.get("netease") or {}).get("mode", "api") != "api":
        return True
    host, port = _netease_addr(cfg)
    if _port_open(host, port):
        return True
    _proxy = proc.popen(
        ["node", NODE_SERVER_JS], cwd=PROJECT_DIR,
        stdout=open(os.path.join(PROJECT_DIR, "netease.out.log"), "w"),
        stderr=subprocess.STDOUT,
    )
    deadline = time.time() + wait
    while time.time() < deadline:
        if _port_open(host, port):
            return True
        time.sleep(0.5)
    return False


def _stop_locked():
    """Terminate the proxy if *we* started it. Caller must hold ``_lock``."""
    global _proxy
    if _proxy is not None and _proxy.poll() is None:
        try:
            _proxy.terminate()
        except Exception:
            pass
    _proxy = None


def ensure_netease_api(wait=15.0):
    """Ensure the proxy is up (no refcount); used by daemon mode / logon task."""
    with _lock:
        return _ensure_locked(wait)


def acquire(wait=15.0):
    """Mark the start of a netease-touching operation (starts proxy if needed).

    Always pair with :func:`release` in a ``finally`` block.
    """
    global _refs
    with _lock:
        ok = True
        if _refs == 0:
            ok = _ensure_locked(wait)
        _refs += 1
        return ok


def release():
    """Mark the end of a netease-touching operation; stops the proxy at ref 0."""
    global _refs
    with _lock:
        if _refs > 0:
            _refs -= 1
        if _refs == 0:
            _stop_locked()


def stop_netease_api():
    """Force-stop the proxy (service shutdown), regardless of the refcount."""
    global _refs
    with _lock:
        _refs = 0
        _stop_locked()


def collect_errors(result):
    return {k: v["error"] for k, v in (result or {}).items()
            if isinstance(v, dict) and "error" in v}


def run_once():
    """One collect → export → push pass.  Returns a summary dict.

    No retry / email here; callers decide.  Stops before publishing when a
    source errored (same as the scheduled run).
    """
    from .collector import collect_once
    from .export_site import export_site, push_site
    result = collect_once()
    errs = collect_errors(result)
    summary = {"push_date": result.get("push_date"), "errors": errs,
               "exported": None, "pushed": None, "push_error": None}
    if errs:
        return summary
    run_status.record("last_collect", result.get("push_date"))
    summary["exported"] = export_site()
    try:
        summary["pushed"] = push_site()
    except Exception as e:
        summary["push_error"] = str(e)
        return summary
    run_status.record("last_push")
    return summary
