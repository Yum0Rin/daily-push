"""登录时一次性采集并推送（无常驻）。

流程：确保网易云代理 → 采集（网易云/B站/公众号）→ 导出 → 推送 Pages → 退出。
采集失败发失败邮件；结束时会关掉**本进程拉起的**网易云代理，不留常驻进程。

由登录启动项 `Startup\\DailyPush.vbs` 调用（pythonw，无控制台）。
07:30 的定时采集由云端 GitHub Actions 负责，本地不再定时。
"""
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from daily_push import pipeline  # noqa: E402

LOG_PATH = os.path.join(PROJECT_DIR, "run_daily.log")


def _log(msg):
    import datetime
    line = f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _email(subject, body):
    try:
        from tools.notify_email import send_email
        send_email(subject, body)
    except Exception as e:
        _log(f"mail error: {e}")


def main():
    import datetime
    _log("run_daily start")
    pipeline.ensure_netease_api()
    try:
        summary = pipeline.run_once()
    except Exception as e:
        summary = {"errors": {"run": str(e)}}
    finally:
        pipeline.stop_netease_api()

    errs = summary.get("errors") or {}
    if errs:
        _log(f"collect errors: {errs}")
        lines = [f"时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                 "失败环节：登录采集 · 采集", ""]
        for k, v in errs.items():
            lines.append(f"· {k}: {v}")
        _email("每日推送 · 本地采集失败", "\n".join(lines))
        return 1
    if summary.get("push_error"):
        _log(f"push error: {summary['push_error']}")
        _email("每日推送 · 本地推送失败",
               f"导出成功，但推送 Pages 失败：{summary['push_error']}")
        return 1
    _log(f"done push_date={summary.get('push_date')} "
         f"pushed={bool(summary.get('pushed'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
