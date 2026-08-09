"""一键启动：拉起 NeteaseCloudMusicApi -> 首次采集 -> Flask 网页 -> 每日定时采集。

用法：
    python start.py            # 启动并执行一次采集
    python start.py --no-collect  # 只启动服务（网页），不手动采集

失败处理：
    - 采集失败：发邮件（本地 · 采集失败）并每 5 分钟耐心重试，网络恢复后自动补上；
    - 推送失败：发邮件（本地 · 推送失败）并后台每 60 秒重试直到成功；
    - 不再桌面弹窗，全部统一邮件通知并标明失败环节。
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

COLLECT_RETRY_INTERVAL = 300  # 采集失败后耐心重试间隔（秒）
PUSH_RETRY_INTERVAL = 60      # 推送失败后后台重试间隔（秒）


def _send_mail(subject, body):
    """发邮件；失败仅打印日志，不影响主流程。"""
    try:
        from tools.notify_email import send_email
        ok = send_email(subject, body)
        print(f"[mail] {'sent' if ok else 'SEND FAILED'}: {subject}")
        return ok
    except Exception as e:
        print(f"[mail] ERROR {e}")
        return False


def _collect_errors(result):
    errs = {}
    for k, v in (result or {}).items():
        if isinstance(v, dict) and "error" in v:
            errs[k] = v["error"]
    return errs


def _report_errors(errs, stage="采集"):
    """本地失败统一发邮件（不再桌面弹窗）。stage 标明失败环节。"""
    if not errs:
        return
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"时间：{today}", f"失败环节：本地 · {stage}", ""]
    for k, v in errs.items():
        lines.append(f"· {k}: {v}")
    lines.append("")
    lines.append("脚本会在后台耐心重试，网络/登录态恢复后自动补上。")
    _send_mail(f"每日推送 · 本地{stage}失败", "\n".join(lines))


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

    Only needed for the ``api`` netease mode. When using ``ncm-cli``
    mode the official CLI replaces the Node proxy entirely, so nothing is
    started here.
    """
    cfg = load_config()
    mode = cfg.get("netease", {}).get("mode", "api")
    if mode != "api":
        print(f"[start] netease mode={mode}, skipping NeteaseCloudMusicApi")
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


def run_collect(stop_at=None):
    """采集 -> 导出 -> 推送。失败则耐心重试直到成功（网络可能稍后才通）。

    stop_at 不为空时，重试到该时刻即放弃（避免阻塞下一次定时采集）。
    """
    print(f"[collect] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} starting...")
    reported = False
    while True:
        try:
            result = collect_once()
            errs = _collect_errors(result)
            if not errs:
                print(f"[collect] done push_date={result.get('push_date')}")
                _export_and_push()
                if reported:
                    print("[collect] 网络/登录态恢复，重试成功")
                return
            print(f"[collect] errors: {errs}")
            if not reported:
                _report_errors(errs)
                reported = True
        except Exception as e:
            print(f"[collect] ERROR {e}")
            if not reported:
                _report_errors({"collect": str(e)})
                reported = True
        if stop_at and datetime.now() >= stop_at:
            print("[collect] give up this cycle (next scheduled run reached)")
            return
        print(f"[collect] retry in {COLLECT_RETRY_INTERVAL}s...")
        time.sleep(COLLECT_RETRY_INTERVAL)


def _export_and_push():
    """导出站点并推送。推送失败：发邮件 + 后台每 60s 重试直到成功。"""
    try:
        from daily_push.export_site import export_site, push_site
        path = export_site()
        try:
            pushed = push_site()
            print(f"[site] exported {path}" + (f" -> {pushed}" if pushed else " (no repo configured)"))
        except Exception as e:
            print(f"[site] push failed: {e}; will retry in background")
            _report_errors({"推送": f"本地已导出，但推送 GitHub 失败（云端站点会缺本地数据，如公众号 mp）：{e}"},
                           stage="推送")
            _start_push_retry()
    except Exception as e:
        print(f"[site] export/push failed: {e}")
        _report_errors({"导出": str(e)}, stage="导出")


_push_retry_lock = threading.Lock()
_push_retry_started = False


def _start_push_retry():
    """后台持续重推 site/index.html，直到成功（网络恢复后自动补上）。"""
    global _push_retry_started
    with _push_retry_lock:
        if _push_retry_started:
            return
        _push_retry_started = True

    def worker():
        global _push_retry_started
        from daily_push.export_site import export_site, push_site
        while True:
            time.sleep(PUSH_RETRY_INTERVAL)
            try:
                export_site()
                pushed = push_site()
                print(f"[site] background push retry succeeded -> {pushed}")
                return
            except Exception as e:
                print(f"[site] background push retry failed: {e}")

    threading.Thread(target=worker, daemon=True).start()


def scheduler_thread(push_time):
    """Run collect once daily at push_time (HH:MM), retrying patiently until
    the next scheduled run if the network is down (e.g. hotspot not connected)."""
    hh, mm = (int(x) for x in push_time.split(":"))
    print(f"[sched] daily collect scheduled at {hh:02d}:{mm:02d}")
    while True:
        now = datetime.now()
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        time.sleep((target - now).total_seconds())
        run_collect(stop_at=target + timedelta(days=1))


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