"""一键启动：拉起 NeteaseCloudMusicApi -> 首次采集 -> Flask 网页 -> 每日定时采集。

用法：
    python start.py            # 启动并执行一次采集
    python start.py --no-collect  # 只启动服务（网页），不手动采集

启动行为（2026-09-12 起）：
    - 静默启动：不再一上来就弹浏览器；
    - **首次采集并成功推送后**才自动打开本地网页（没推送完不弹）；
    - 失败处理：采集失败发邮件并每 5 分钟耐心重试；推送失败发邮件并后台每 60 秒重试。
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

from daily_push import run_status
from daily_push.config import load_config
from daily_push.collector import collect_once
from daily_push.publish_lock import LockBusy, heavy_lock

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NODE_SERVER_JS = os.path.join(PROJECT_DIR, "netease_server.js")

COLLECT_RETRY_INTERVAL = 300  # 采集失败后耐心重试间隔（秒）
PUSH_RETRY_INTERVAL = 60      # 推送失败后后台重试间隔（秒）
HEAVY_LOCK_TIMEOUT = 900      # 跨进程发布锁最长等待（秒）

# Set once the first collect cycle has been exported AND pushed successfully.
_first_push_event = threading.Event()


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
    subject = f"每日推送 · 本地{stage}失败"
    if stage == "采集":
        try:
            from tools.cookie_reply import is_cookie_error
            from tools.trigger_cookie_repair import trigger
            cookie_sources = [s for s in ("netease", "bilibili") if is_cookie_error(s, errs.get(s))]
            if cookie_sources:
                ref = f"{datetime.now().strftime('%Y-%m-%d')}-{'-'.join(cookie_sources)}"
                subject = f"{subject} ref={ref}"
                trigger(cookie_sources, datetime.now().strftime("%Y-%m-%d"))
        except Exception as e:
            print(f"[cookie-repair] 本地触发云端轮询失败: {e}")
    _send_mail(subject, "\n".join(lines))


def _try_apply_reply_cookie(errs):
    """本地自愈：从邮箱回复中读取新 cookie 并写回 config.json，下次重试直接生效。"""
    try:
        from tools.cookie_reply import (is_cookie_error, imap_find_reply,
                                        extract_cookies, apply_local_config)
        sources = [s for s in ("netease", "bilibili") if is_cookie_error(s, errs.get(s))]
        if not sources:
            return
        ref = f"{datetime.now().strftime('%Y-%m-%d')}-{'-'.join(sources)}"
        body = imap_find_reply(ref, since_days=2)
        if not body:
            print(f"[cookie-reply] 邮箱暂无回复（ref={ref}）")
            return
        cookies = extract_cookies(body, sources)
        if cookies:
            changed = apply_local_config(cookies)
            print(f"[cookie-reply] 已应用回复中的新 cookie: {changed}")
        else:
            print("[cookie-reply] 回复解析失败")
    except Exception as e:
        print(f"[cookie-reply] ERROR {e}")


def _port_open(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def ensure_netease_api():
    """Ensure NeteaseCloudMusicApi is listening on :3000; spawn if needed."""
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
        errs = None
        try:
            with heavy_lock(timeout=HEAVY_LOCK_TIMEOUT):
                result = collect_once()
                errs = _collect_errors(result)
                if not errs:
                    print(f"[collect] done push_date={result.get('push_date')}")
                    run_status.record("last_collect", result.get("push_date"))
                    ok = _export_and_push()
                    if reported and ok:
                        print("[collect] 网络/登录态恢复，重试成功")
                    return
        except LockBusy:
            print("[collect] 另一个发布任务在运行，稍后重试")
        except Exception as e:
            print(f"[collect] ERROR {e}")
            errs = {"collect": str(e)}

        if errs:
            print(f"[collect] errors: {errs}")
            if not reported:
                _report_errors(errs)
                reported = True
            _try_apply_reply_cookie(errs)
        if stop_at and datetime.now() >= stop_at:
            print("[collect] give up this cycle (next scheduled run reached)")
            return
        print(f"[collect] retry in {COLLECT_RETRY_INTERVAL}s...")
        time.sleep(COLLECT_RETRY_INTERVAL)


def _export_and_push():
    """导出站点并推送。失败：发邮件 + 后台每 60s 重试。成功返回 True。"""
    try:
        from daily_push.export_site import export_site, push_site
        path = export_site()
    except Exception as e:
        print(f"[site] export failed: {e}")
        _report_errors({"导出": str(e)}, stage="导出")
        _start_push_retry()
        return False

    try:
        pushed = push_site()
        print(f"[site] exported {path}" + (f" -> {pushed}" if pushed else " (no repo configured)"))
        run_status.record("last_push")
        _first_push_event.set()
        return True
    except Exception as e:
        print(f"[site] push failed: {e}; will retry in background")
        _report_errors({"推送": f"本地已导出，但推送 GitHub 失败（云端站点会缺本地数据，如公众号 mp）：{e}"},
                       stage="推送")
        _start_push_retry()
        return False


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
                with heavy_lock(timeout=HEAVY_LOCK_TIMEOUT):
                    export_site()
                    pushed = push_site()
                print(f"[site] background push retry succeeded -> {pushed}")
                run_status.record("last_push")
                _first_push_event.set()
                return
            except LockBusy:
                print("[site] background retry: another task running, will retry")
            except Exception as e:
                print(f"[site] background push retry failed: {e}")

    threading.Thread(target=worker, daemon=True).start()


def _current_push_time(default):
    try:
        return load_config().get("push_time", default) or default
    except Exception:
        return default


def scheduler_thread(default_push_time):
    """Daily collect at push_time (HH:MM); re-reads settings so edits apply live."""
    print(f"[sched] daily collect scheduled at {default_push_time}")
    while True:
        push_time = _current_push_time(default_push_time)
        try:
            hh, mm = (int(x) for x in push_time.split(":"))
        except Exception:
            hh, mm = (int(x) for x in default_push_time.split(":"))
        now = datetime.now()
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        while datetime.now() < target:
            remaining = (target - datetime.now()).total_seconds()
            time.sleep(min(30, max(0.5, remaining)))
            if _current_push_time(default_push_time) != push_time:
                print("[sched] push_time changed, rescheduling")
                break
        else:
            run_collect(stop_at=target + timedelta(days=1))


def open_dashboard(host, port, wait_event=None):
    """Wait for the server (and, if given, the first successful push), then open browser."""
    def _wait():
        for _ in range(60):
            try:
                with socket.create_connection((host, port), timeout=1):
                    break
            except OSError:
                time.sleep(0.5)
        if wait_event is not None:
            print("[start] waiting for first successful push before opening the page ...")
            wait_event.wait()
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
    else:
        _first_push_event.set()

    from daily_push.app import create_app
    cfg = load_config()
    port = int(cfg.get("port", 5000))
    push_time = cfg.get("push_time", "07:30")

    thread = threading.Thread(target=scheduler_thread, args=(push_time,), daemon=True)
    thread.start()

    print(f"[start] open http://127.0.0.1:{port}  (Ctrl+C to stop)")
    open_dashboard("127.0.0.1", port, wait_event=_first_push_event)
    create_app().run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
