"""Daily pipeline: netease proxy lifecycle + one collect→export→push pass.

Shared by:
- ``start.py`` (daemon mode, manual ``python start.py``),
- ``tools/run_daily.py`` (Windows Task Scheduler one-shot: logon + 07:30),
- ``daily_push/app.py`` (settings page 「手动推送」).
"""
import os
import socket
import subprocess
import time

from . import proc
from . import run_status

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE_SERVER_JS = os.path.join(PROJECT_DIR, "netease_server.js")

# The NeteaseCloudMusicApi process we spawned (None if it was already running).
_proxy = None


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


def ensure_netease_api(cfg=None, wait=15.0):
    """Ensure NeteaseCloudMusicApi is listening; spawn if needed.

    Returns True if it is up.  Remembers the process we spawned so
    :func:`stop_netease_api` can clean it up.
    """
    global _proxy
    from .config import load_config
    cfg = cfg or load_config()
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


def stop_netease_api():
    """Terminate the proxy only if *this* process started it."""
    global _proxy
    if _proxy is not None and _proxy.poll() is None:
        try:
            _proxy.terminate()
        except Exception:
            pass
    _proxy = None


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
