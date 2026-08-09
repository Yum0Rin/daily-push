"""根据报错信息判断是否有 cookie/登录类错误，并触发云端 cookie-repair 轮询工作流。

本地（start.py）和云端（daily-collect）共用：
- 云端：读取 cloud_status.json 里的 errors，判定后触发。
- 本地：直接调用 detect_sources(errs) / trigger(sources, push_date)。

ref 规则与报错邮件主题保持一致：ref={push_date}-{'-'.join(sources)}
"""
import json
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from tools.cookie_reply import is_cookie_error  # noqa: E402

REPO = os.environ.get("GITHUB_REPOSITORY", "").strip() or "Yum0Rin/daily-push"


def detect_sources(errs):
    """返回需要修 cookie 的来源列表，如 ['netease', 'bilibili']。"""
    out = []
    for s in ("netease", "bilibili"):
        if is_cookie_error(s, errs.get(s)):
            out.append(s)
    return out


def build_ref(push_date, sources):
    return f"{push_date or 'today'}-{'-'.join(sources)}"


def trigger(sources, push_date=None, timeout_min=360):
    """通过 gh 触发 cookie-repair 工作流。返回 ref；未触发返回 None。"""
    if not sources:
        return None
    ref = build_ref(push_date, sources)
    cmd = [
        "gh", "workflow", "run", "cookie-repair.yml",
        "-f", f"sources={','.join(sources)}",
        "-f", f"ref={ref}",
        "-f", f"timeout_min={timeout_min}",
        "--repo", REPO,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            print(f"[cookie-repair] 已触发云端轮询 sources={sources} ref={ref}")
            return ref
        print(f"[cookie-repair] 触发失败: {r.stderr.strip() or r.stdout.strip()}")
    except Exception as e:
        print(f"[cookie-repair] 触发异常: {e}")
    return None


def main():
    """云端入口：从 cloud_status.json 判定并触发。"""
    status = {}
    try:
        with open(os.path.join(BASE_DIR, "cloud_status.json"), encoding="utf-8") as f:
            status = json.load(f)
    except Exception:
        pass
    push_date = status.get("push_date")
    errs = status.get("errors") or {}
    sources = detect_sources(errs)
    if not sources:
        print("[cookie-repair] 无 cookie 类错误，跳过")
        return
    trigger(sources, push_date)


if __name__ == "__main__":
    main()
