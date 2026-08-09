"""GitHub Actions 端：轮询邮箱等待用户回复新 Cookie。

触发：workflow_dispatch（由 daily-collect 或本地 start.py 触发）。
流程：每 10 分钟 IMAP 查一次回复；收到后验证 -> 更新 Secrets -> 发结果邮件 -> 停止。
超时（默认 6 小时）后发超时邮件并停止。

环境变量：
    SOURCES            需要更新的来源，逗号分隔（netease,bilibili）
    REF                报错邮件主题里的 ref 标记
    REPLY_TIMEOUT_MIN  最长等待分钟数（默认 360）
    GH_TOKEN           用于 gh secret set 的 PAT（repo 权限）
    SMTP_*             发结果邮件用
    RUN_URL            运行链接
"""
import os
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from tools.cookie_reply import imap_find_reply, extract_cookies, test_cookie  # noqa: E402
from tools.notify_email import send_email  # noqa: E402

POLL_INTERVAL = 600  # 10 分钟
REPO = os.environ.get("GITHUB_REPOSITORY", "").strip() or "Yum0Rin/daily-push"
SECRET_NAMES = {"netease": "NETEASE_COOKIE", "bilibili": "BILIBILI_SESSDATA"}


def _gh_secret_set(name, value):
    r = subprocess.run(
        ["gh", "secret", "set", name, "--repo", REPO, "--body", value],
        capture_output=True, text=True, timeout=60,
    )
    return r.returncode == 0


def main():
    sources = [s.strip() for s in os.environ.get("SOURCES", "").split(",") if s.strip()]
    ref = os.environ.get("REF", "").strip()
    timeout_min = int(os.environ.get("REPLY_TIMEOUT_MIN", "360"))
    run_url = os.environ.get("RUN_URL", "")
    if not sources or not ref:
        print("ERROR: SOURCES / REF 未配置")
        sys.exit(1)

    deadline = time.time() + timeout_min * 60
    print(f"[cookie-repair] sources={sources} ref={ref} 等待回复最多 {timeout_min} 分钟")

    while time.time() < deadline:
        body = imap_find_reply(ref, since_days=3)
        if body:
            print("[cookie-repair] 找到回复，开始解析")
            cookies = extract_cookies(body, sources)
            missing = [s for s in sources if s not in cookies]
            results = {}
            for src, val in cookies.items():
                ok, detail = test_cookie(src, val)
                print(f"[cookie-repair] {src}: {detail}")
                results[src] = (ok, val, detail)

            if not missing and all(results[s][0] for s in sources):
                ok_all = True
                for src in sources:
                    if not _gh_secret_set(SECRET_NAMES[src], results[src][1]):
                        ok_all = False
                        print(f"[cookie-repair] 更新 {SECRET_NAMES[src]} 失败")
                if ok_all:
                    lines = [f"来源：{' / '.join(sources)}", ""]
                    for src in sources:
                        lines.append(f"· {src}: {results[src][2]}")
                    lines.append("")
                    lines.append("已更新 GitHub Secrets，云端下次采集直接用新 Cookie。")
                    if run_url:
                        lines.append(f"运行链接：{run_url}")
                    send_email("每日推送 · Cookie 已更新并验证通过", "\n".join(lines))
                    print("[cookie-repair] 成功，退出")
                    sys.exit(0)
                send_email("每日推送 · Cookie 更新失败",
                           "验证通过但更新 GitHub Secrets 失败（请检查 REPO_TOKEN 权限）。")
                sys.exit(1)

            lines = [f"来源：{' / '.join(sources)}", ""]
            for s in sources:
                if s in missing:
                    lines.append(f"· {s}: 未能从回复中解析出 Cookie（请检查粘贴格式，一行一个、不带前缀）")
                else:
                    ok, _, detail = results[s]
                    lines.append(f"· {s}: {'通过' if ok else '无效'} — {detail}")
            lines.append("")
            lines.append("如确需继续，请下次报错时重新回复新 Cookie。")
            send_email("每日推送 · Cookie 无效，请重新回复", "\n".join(lines))
            print("[cookie-repair] 验证失败，退出")
            sys.exit(1)

        remain = int(deadline - time.time())
        print(f"[cookie-repair] 暂无回复，约 {max(remain, 0) // 60} 分钟后再次检查")
        time.sleep(min(POLL_INTERVAL, max(remain, 1)))

    print("[cookie-repair] 超时未收到回复")
    send_email("每日推送 · 等待新 Cookie 回复超时",
               f"来源：{' / '.join(sources)}\n\n{timeout_min} 分钟内未收到有效回复，已停止轮询。"
               f"\n如需更新，请让脚本下次报错时重新触发。")
    sys.exit(0)


if __name__ == "__main__":
    main()
