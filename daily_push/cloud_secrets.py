"""Push platform credentials to GitHub Actions Secrets via the ``gh`` CLI.

Local → cloud sync: after the local settings page saves a cookie to
``config.json``, it can mirror the value into the repo's Actions Secrets so the
cloud collector uses the same credential.  The email-based cookie-repair flow
stays in place as the away-from-PC fallback.

Auth: uses the local ``gh`` CLI.  If ``gh auth`` is already logged in nothing
else is needed; otherwise a PAT can be provided via config ``github.token``
(passed as ``GH_TOKEN``).  Secrets are written through stdin so the value never
appears in the process command line.
"""
import os
import shutil
import subprocess

SECRET_NAMES = {"netease": "NETEASE_COOKIE", "bilibili": "BILIBILI_SESSDATA"}


def _run(args, timeout=60, env=None, input=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, env=e, input=input,
    )


def gh_available():
    return shutil.which("gh") is not None


def gh_auth_status():
    """Return ``(ok, detail)`` describing local gh availability / login."""
    if not gh_available():
        return False, "未检测到 gh CLI（请安装并执行 gh auth login）"
    try:
        r = _run(["gh", "auth", "status"], timeout=30)
    except Exception as e:
        return False, f"gh 检测失败：{e}"
    if r.returncode == 0:
        return True, "gh 已登录"
    msg = ((r.stderr or "") + (r.stdout or "")).strip()
    return False, (msg[:200] or "gh 未登录")


def _repo_token(cfg):
    repo = str((cfg.get("site") or {}).get("repo") or "").strip()
    token = (cfg.get("github") or {}).get("token") or None
    return repo, token


def cloud_status(cfg):
    repo, token = _repo_token(cfg)
    ok, detail = gh_auth_status()
    available = bool(ok and repo)
    if ok and not repo:
        detail = "未配置 site.repo"
    return {
        "available": available,
        "authed": ok,
        "repo": repo,
        "token_configured": bool(token),
        "detail": detail,
    }


def set_secret(name, value, repo, token=None):
    """Set one Actions Secret. Returns ``(ok, detail)``; never raises."""
    if not repo:
        return False, "未配置 site.repo"
    if not value:
        return False, "凭证为空"
    env = {"GH_TOKEN": token} if token else None
    try:
        r = _run(["gh", "secret", "set", name, "--repo", repo], env=env, input=value)
    except Exception as e:
        return False, f"调用 gh 失败：{e}"
    if r.returncode == 0:
        return True, f"已更新 {name}"
    msg = ((r.stderr or "") + (r.stdout or "")).strip()
    return False, (msg[:300] or "gh secret set 失败")


def sync_cookies(cfg, values):
    """Push ``{source: value}`` to Secrets. Returns ``{source: {ok, detail}}``."""
    repo, token = _repo_token(cfg)
    out = {}
    for src, val in (values or {}).items():
        name = SECRET_NAMES.get(src)
        if not name:
            continue
        ok, detail = set_secret(name, val, repo, token)
        out[src] = {"ok": ok, "detail": detail}
    return out
