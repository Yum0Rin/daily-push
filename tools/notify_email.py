"""GitHub Actions 云端采集出错时发邮件通知。

读取 cloud_status.json（由 cloud_collect.py 生成）：
- errors 非空 → 发邮件列出失败模块与原因
- 文件缺失 → 说明工作流在生成结果前就失败了（依赖安装/网络等）
- 无错误 → 不发邮件

需要 GitHub Secrets（在 Settings -> Secrets 配置）：
    SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS / MAIL_TO
QQ 邮箱示例：SMTP_HOST=smtp.qq.com, SMTP_PORT=465,
SMTP_USER=<QQ号>@qq.com, SMTP_PASS=授权码（非登录密码）, MAIL_TO=收件地址
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


def _load_status():
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _send(subject, body):
    host = os.environ.get("SMTP_HOST", "").strip()
    port = os.environ.get("SMTP_PORT", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    pwd = os.environ.get("SMTP_PASS", "").strip()
    to = os.environ.get("MAIL_TO", "").strip()
    if not all([host, port, user, pwd, to]):
        print("ERROR: SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS/MAIL_TO 未全部配置，无法发邮件")
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


def main():
    status = _load_status()
    run_url = os.environ.get("RUN_URL", "")
    push_date = (status or {}).get("push_date", "?")
    if status is None:
        subject = "每日推送 · 云端工作流提前失败"
        body = "云端采集工作流在生成结果前就失败了（依赖安装/网络等），请查看 Actions 日志。\n"
    elif status.get("errors"):
        errs = status["errors"]
        lines = [f"推送日期：{push_date}", ""]
        for k, v in errs.items():
            lines.append(f"· {k}: {v}")
        lines.append("")
        lines.append("多半是 Cookie / 登录态过期或网络问题，请更新 Secrets 后重试。")
        subject = f"每日推送 · 云端采集失败 {push_date}"
        body = "\n".join(lines)
    else:
        print("no errors, skip email")
        return
    if run_url:
        body += f"\n运行链接：{run_url}"
    if not _send(subject, body):
        sys.exit(1)


if __name__ == "__main__":
    main()
