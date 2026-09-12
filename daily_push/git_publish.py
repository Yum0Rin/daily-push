"""Git helper for publishing local settings.json to the ``code`` branch.

The local settings page may commit/push **only** ``settings.json`` (non-secret
policy). Source code is never committed from the web UI, and credentials
(``config.json``) are gitignored so they can never be included.
"""
import os
import subprocess

SETTINGS_FILENAME = "settings.json"
DEFAULT_BRANCH = "code"


def _run(args, cwd, timeout=120):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, env=env,
    )


def _current_branch(repo_dir):
    r = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_dir, timeout=30)
    b = (r.stdout or "").strip()
    return b if b and b != "HEAD" else None


def commit_and_push_settings(repo_dir, remote="origin", branch=None,
                             message=None, push=True):
    """Commit only ``settings.json`` and (optionally) push it.

    Returns ``{"committed": bool, "pushed": bool, "detail": str}``; never raises.
    """
    path = SETTINGS_FILENAME
    if not os.path.exists(os.path.join(repo_dir, path)):
        return {"committed": False, "pushed": False, "detail": "settings.json 不存在"}
    try:
        status = _run(["git", "status", "--porcelain", "--", path], repo_dir, timeout=30)
        if not (status.stdout or "").strip():
            return {"committed": False, "pushed": False, "detail": "settings.json 无变化"}

        add = _run(["git", "add", "--", path], repo_dir, timeout=30)
        if add.returncode != 0:
            return {"committed": False, "pushed": False,
                    "detail": f"git add 失败：{(add.stderr or '').strip()[:200]}"}

        msg = message or "chore: 更新 settings.json（本地设置页）"
        commit = _run(["git", "commit", "-m", msg, "--", path], repo_dir, timeout=60)
        if commit.returncode != 0:
            return {"committed": False, "pushed": False,
                    "detail": f"git commit 失败：{(commit.stderr or '').strip()[:200]}"}

        if not push:
            return {"committed": True, "pushed": False, "detail": "已提交（未推送）"}

        ref_branch = branch or _current_branch(repo_dir) or DEFAULT_BRANCH
        pushed = _run(["git", "push", remote, f"HEAD:{ref_branch}"], repo_dir, timeout=180)
        if pushed.returncode != 0:
            err = (pushed.stderr or pushed.stdout or "").strip()
            return {"committed": True, "pushed": False,
                    "detail": f"git push 失败：{err[:300]}"}
        return {"committed": True, "pushed": True,
                "detail": f"已推送到 {remote}/{ref_branch}"}
    except subprocess.TimeoutExpired:
        return {"committed": False, "pushed": False, "detail": "git 操作超时"}
    except Exception as e:  # pragma: no cover - defensive
        return {"committed": False, "pushed": False, "detail": str(e)}
