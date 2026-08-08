"""一键启动：拉起 NeteaseCloudMusicApi -> 首次采集 -> Flask 网页 -> 每日定时采集。

用法：
    python start.py            # 启动并执行一次采集
    python start.py --no-collect  # 只启动服务（网页），不手动采集

采集出错时：在桌面生成 collect_error.txt 并自动弹出（每天最多弹一次）；
服务就绪后：自动打开浏览器到仪表盘。
"""
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from daily_push.config import load_config
from daily_push.collector import collect_once

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NODE_SERVER_JS = os.path.join(PROJECT_DIR, "netease_server.js")

ERROR_TXT = "collect_error.txt"
ERROR_MARKER = ".collect_error_popped"


def _error_dir():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if os.path.isdir(desktop):
        return desktop
    return os.path.join(PROJECT_DIR, "data")


def _collect_errors(result):
    errs = {}
    for k, v in (result or {}).items():
        if isinstance(v, dict) and "error" in v:
            errs[k] = v["error"]
    return errs


def _report_errors(errs):
    if not errs:
        return
    d = _error_dir()
    os.makedirs(d, exist_ok=True)
    txt = os.path.join(d, ERROR_TXT)
    marker = os.path.join(d, ERROR_MARKER)
    lines = [
        "每日推送 · 采集出错通知",
        f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "以下来源采集失败：",
    ]
    for k, v in errs.items():
        lines.append(f"  · {k}: {v}")
    lines.append("")
    lines.append("多半是 Cookie / 登录态过期，请更新 config.json 后重启。")
    try:
        with open(txt, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        return
    today = datetime.now().strftime("%Y-%m-%d")
    popped = ""
    try:
        with open(marker, "r", encoding="utf-8") as f:
            popped = f.read().strip()
    except Exception:
        pass
    if popped != today:
        try:
            with open(marker, "w", encoding="utf-8") as f:
                f.write(today)
            os.startfile(txt)
        except Exception:
            pass


def _clear_error_report():
    d = _error_dir()
    for name in (ERROR_TXT, ERROR_MARKER):
        try:
            p = os.path.join(d, name)
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


def _port_open(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def ensure_netease_api():
    """Ensure NeteaseCloudMusicApi is listening on :3000; spawn if needed.

    Only needed for the legacy ``api`` netease mode. When using ``ncm-cli``
    mode the official CLI replaces the Node proxy entirely, so nothing is
    started here.
    """
    cfg = load_config()
    mode = cfg.get("netease", {}).get("mode", "ncm-cli")
    if mode != "api":
        print("[start] netease mode=ncm-cli, skipping NeteaseCloudMusicApi")
        return
    base = cfg.get("netease", {}).get("base_url", "http://localhost:3000")
    _, _, rest = base.partition("://")
    host, _, port = rest.partition(":")
    port = int(port)
    if _port_open(host, port):
        print(f"[start] NeteaseCloudMusicApi already on {host}:{port}")
        return
    print(f"[start] starting NeteaseCloudMusicApi on {host}:{port} ...")
    subprocess.Popen(
        ["node", NODE_SERVER_JS],
        cwd=PROJECT_DIR,
        stdout=open(os.path.join(PROJECT_DIR, "netease.out.log"), "w"),
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    for _ in range(30):
        if _port_open(host, port):
            print("[start] NeteaseCloudMusicApi ready")
            return
        time.sleep(0.5)
    print("[start] WARNING: NeteaseCloudMusicApi did not come up in time")


def run_collect():
    """Collect all sources (wrapped in a daemon thread when invoked from CLI)."""
    print(f"[collect] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} starting...")
    try:
        result = collect_once()
        errs = _collect_errors(result)
        if errs:
            print(f"[collect] errors: {errs}")
            _report_errors(errs)
        else:
            _clear_error_report()
        print(f"[collect] done push_date={result.get('push_date')}")
        _export_and_push()
    except Exception as e:
        print(f"[collect] ERROR {e}")
        _report_errors({"collect": str(e)})


def _export_and_push():
    try:
        from daily_push.export_site import export_site, push_site
        path = export_site()
        pushed = push_site()
        print(f"[site] exported {path}" + (f" -> {pushed}" if pushed else " (no repo configured)"))
    except Exception as e:
        print(f"[site] export/push failed: {e}")


def scheduler_thread(push_time):
    """Run collect once daily at push_time (HH:MM)."""
    hh, mm = (int(x) for x in push_time.split(":"))
    print(f"[sched] daily collect scheduled at {hh:02d}:{mm:02d}")
    while True:
        now = datetime.now()
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        time.sleep((target - now).total_seconds())
        run_collect()


def open_dashboard(host, port):
    """Wait until the server is up, then open the dashboard in the default browser."""
    def _wait():
        for _ in range(60):
            try:
                with socket.create_connection((host, port), timeout=1):
                    break
            except OSError:
                time.sleep(0.5)
        try:
            webbrowser.open(f"http://{host}:{port}")
        except Exception:
            pass
    threading.Thread(target=_wait, daemon=True).start()


def main():
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    do_collect = "--no-collect" not in sys.argv
    ensure_netease_api()
    if do_collect:
        threading.Thread(target=run_collect, daemon=True).start()

    from daily_push.app import create_app
    cfg = load_config()
    port = int(cfg.get("port", 5000))
    push_time = cfg.get("push_time", "07:30")

    thread = threading.Thread(target=scheduler_thread, args=(push_time,), daemon=True)
    thread.start()

    print(f"[start] open http://127.0.0.1:{port}  (Ctrl+C to stop)")
    open_dashboard("127.0.0.1", port)
    create_app().run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()