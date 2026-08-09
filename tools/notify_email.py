"""采集/推送失败通知：云端和本地统一走 SMTP 邮件。

- 云端（GitHub Actions）：读取 cloud_status.json，SMTP 配置来自环境变量 SMTP_*（GitHub Secrets）。
- 本地（start.py）：直接调用 send_email()，SMTP 配置来自 config.json 的 email 段。

邮件主题统一带前缀区分来源：
    · 每日推送 · 云端采集失败 / 云端工作流提前失败
    · 每日推送 · 本地采集失败
    · 每日推送 · 本地推送失败
"""
import json
import os
import smtplib
import sys
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_FILE = os.path.join(BASE_DIR, "cloud_status.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")


def _config_email():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("email") or {}
    except Exception:
        return {}


def _resolve_smtp():
    """返回 (host, port, user, pwd, to)。云端优先环境变量，本地回退 config。"""
    email = _config_email()
    host = os.environ.get("SMTP_HOST") or email.get("smtp_host")
    port = os.environ.get("SMTP_PORT") or str(email.get("smtp_port") or "")
    user = os.environ.get("SMTP_USER") or email.get("smtp_user")
    pwd = os.environ.get("SMTP_PASS") or email.get("smtp_pass")
    to = os.environ.get("MAIL_TO") or email.get("mail_to")
    return host, port, user, pwd, to


def send_email(subject, body):
    """发送邮件；SMTP 未配置或发送失败返回 False。"""
    host, port, user, pwd, to = _resolve_smtp()
    if not all([host, port, user, pwd, to]):
        print("ERROR: 邮件 SMTP 未配置（本地需 config.json 的 email 段，云端需 SMTP_* Secrets）")
        return False
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header("每日推送", "utf-8")), user))
    msg["To"] = to
    try:
        if int(port) == 465:
            s = smtplib.SMTP_SSL(host, int(port), timeout=30)
        else:
            s = smtplib.SMTP(host, int(port), timeout=30)
            s.starttls()
        s.login(user, pwd)
        s.sendmail(user, [to], msg.as_string())
        s.quit()
        return True
    except Exception as e:
        print(f"ERROR: 邮件发送失败: {e}")
        return False


def _cookie_sources(errs):
    try:
        from tools.cookie_reply import is_cookie_error
        return [s for s in ("netease", "bilibili") if is_cookie_error(s, errs.get(s))]
    except Exception:
        return []


def main():
    """云端入口：读取 cloud_status.json，有错误才发邮件。"""
    run_url = os.environ.get("RUN_URL", "")
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            status = json.load(f)
    except Exception:
        status = None
    push_date = (status or {}).get("push_date", "?")
    if status is None:
        subject = "每日推送 · 云端工作流提前失败"
        body = "云端采集工作流在生成结果前就失败了（依赖安装/网络等），请查看 Actions 日志。"
    elif status.get("errors"):
        errs = status["errors"]
        lines = [f"推送日期：{push_date}", ""]
        for k, v in errs.items():
            lines.append(f"· {k}: {v}")
        lines.append("")
        lines.append("多半是 Cookie / 登录态过期或网络问题，请更新 Secrets 后重试。")
        subject = f"每日推送 · 云端采集失败 {push_date}"
        if _cookie_sources(errs):
            ref = f"{push_date}-{'-'.join(_cookie_sources(errs))}"
            subject = f"{subject} ref={ref}"
        body = "\n".join(lines)
    else:
        print("no errors, skip email")
        return
    if run_url:
        body += f"\n运行链接：{run_url}"
    if not send_email(subject, body):
        sys.exit(1)


if __name__ == "__main__":
    main()
