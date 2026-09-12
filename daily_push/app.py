"""Flask web app: serve the daily dashboard + history browsing + trigger collect.

Also serves a **local-only** settings page (``/settings``) that edits policy
(``settings.json``) and credentials (``config.json``).  All ``/api/`` routes are
guarded against CSRF / DNS-rebinding: requests must target a loopback host and
carry the per-run settings token.  The settings page is intentionally NOT part of
the exported static site (see ``export_site.py``).
"""
import datetime
import os
import secrets
import sys
import threading
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request

from .config import load_config
from .collector import collect_once
from .settings_store import (
    SettingsError,
    policy_view,
    save_policy,
    save_secrets,
    secrets_view,
)
from .storage import Storage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _host_ok(host):
    h = (host or "").rsplit(":", 1)[0].strip("[]").lower()
    return h in _LOCAL_HOSTS


def _origin_ok(origin):
    try:
        return (urlparse(origin).hostname or "").lower() in _LOCAL_HOSTS
    except Exception:
        return False


def _normalize(source, value):
    """Best-effort credential cleanup, reusing the cookie-repair parser."""
    try:
        from tools.cookie_reply import _normalize_cookie
        return _normalize_cookie(source, value or "") or (value or "").strip()
    except Exception:
        return (value or "").strip()


def create_app(config_path=None, settings_path=None):
    app = Flask(__name__)
    app.config["SETTINGS_TOKEN"] = secrets.token_urlsafe(32)

    cfg0 = load_config(config_path, settings_path)
    storage = Storage(os.path.join(PROJECT_DIR, cfg0.get("data_dir", "data")))

    def _cfg():
        return load_config(config_path, settings_path)

    # ------------------------------------------------------------------ guard
    @app.before_request
    def _guard_api():
        if not request.path.startswith("/api/"):
            return None
        if not _host_ok(request.host):
            return jsonify({"error": "forbidden host"}), 403
        if request.method != "GET":
            origin = request.headers.get("Origin") or request.headers.get("Referer")
            if origin and not _origin_ok(origin):
                return jsonify({"error": "forbidden origin"}), 403
        if request.path.startswith("/api/settings"):
            token = request.headers.get("X-CSRF-Token")
            if not token or not secrets.compare_digest(token, app.config["SETTINGS_TOKEN"]):
                return jsonify({"error": "invalid csrf token"}), 403
        return None

    # -------------------------------------------------------------- dashboard
    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/settings")
    def settings_page():
        return render_template("settings.html", csrf_token=app.config["SETTINGS_TOKEN"])

    @app.route("/api/dates")
    def dates():
        return jsonify({"dates": storage.list_dates()})

    @app.route("/api/today")
    def today():
        return jsonify(storage.get(datetime.date.today().isoformat()) or {"push_date": datetime.date.today().isoformat()})

    @app.route("/api/day/<date_str>")
    def day(date_str):
        return jsonify(storage.get(date_str) or {"error": "no data", "push_date": date_str})

    # One heavy operation (collect / purge+publish) at a time: they touch the
    # SQLite DB and the site/ git repo, so they must never run concurrently.
    _heavy_lock = threading.Lock()
    _state = {
        "running": False,
        "done": False,
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
    }
    _state_lock = threading.Lock()

    def _run_collect():
        with _state_lock:
            _state["running"] = True
            _state["done"] = False
            _state["started_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            _state["error"] = None
        try:
            result = collect_once()
            with _state_lock:
                _state["result"] = result
            errs = {k: v.get("error") for k, v in result.items()
                    if isinstance(v, dict) and "error" in v}
            if errs:
                try:
                    from tools.notify_email import send_email
                    lines = [f"时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                             "失败环节：本地 · 采集（网页手动触发）", ""]
                    for k, v in errs.items():
                        lines.append(f"· {k}: {v}")
                    send_email("每日推送 · 本地采集失败", "\n".join(lines))
                except Exception:
                    pass
        except Exception as e:
            with _state_lock:
                _state["error"] = str(e)
        finally:
            with _state_lock:
                _state["running"] = False
                _state["done"] = True
                _state["finished_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            _heavy_lock.release()

    @app.route("/api/collect", methods=["POST"])
    def trigger_collect():
        if not _heavy_lock.acquire(blocking=False):
            return jsonify({"error": "另一个任务正在运行"}), 429
        threading.Thread(target=_run_collect, daemon=True).start()
        return jsonify({"status": "started"})

    @app.route("/api/collect/status")
    def collect_status():
        with _state_lock:
            return jsonify({
                "running": _state["running"],
                "done": _state["done"],
                "started_at": _state["started_at"],
                "finished_at": _state["finished_at"],
                "error": _state["error"],
                "push_date": (_state["result"] or {}).get("push_date"),
            })

    @app.route("/api/status")
    def status():
        cfg = _cfg()
        today_row = storage.get(datetime.date.today().isoformat())
        return jsonify({
            "today_pushed": bool(today_row),
            "history_days": len(storage.list_dates()),
            "config": {
                "push_time": cfg.get("push_time", "08:30"),
                "bilibili_configured": bool(cfg.get("bilibili", {}).get("sessdata")),
                "netease_configured": bool(cfg.get("netease", {}).get("cookie")),
            },
        })

    # --------------------------------------------------------------- settings
    @app.route("/api/settings")
    def api_settings_get():
        return jsonify({
            "policy": policy_view(settings_path),
            "secrets": secrets_view(config_path),
        })

    @app.route("/api/settings/policy", methods=["POST"])
    def api_settings_policy():
        body = request.get_json(silent=True) or {}
        try:
            saved = save_policy(body.get("policy") or {}, settings_path)
        except SettingsError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True, "policy": saved})

    @app.route("/api/settings/secrets", methods=["POST"])
    def api_settings_secrets():
        body = request.get_json(silent=True) or {}
        updates = body.get("secrets") or {}
        normalized = {}
        for source in ("netease", "bilibili"):
            if source in updates:
                value = updates[source]
                if isinstance(value, dict):
                    value = value.get("cookie" if source == "netease" else "sessdata")
                if value:
                    normalized[source] = (
                        {"cookie": _normalize(source, value)} if source == "netease"
                        else {"sessdata": _normalize(source, value)})
        try:
            save_secrets(normalized, config_path)
        except SettingsError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True, "secrets": secrets_view(config_path)})

    @app.route("/api/settings/verify", methods=["POST"])
    def api_settings_verify():
        body = request.get_json(silent=True) or {}
        source = body.get("source")
        value = _normalize(source, body.get("value") or "")
        if source not in ("netease", "bilibili"):
            return jsonify({"error": "未知来源"}), 400
        if not value:
            return jsonify({"ok": False, "detail": "未填写凭证"})
        cfg = _cfg()
        try:
            from tools.cookie_reply import test_cookie
            base = (cfg.get("netease") or {}).get("base_url") or "http://localhost:3000"
            ok, detail = test_cookie(source, value, base)
        except Exception as e:
            ok, detail = False, f"检测失败：{e}"
        return jsonify({"ok": bool(ok), "detail": detail})

    @app.route("/api/settings/check", methods=["POST"])
    def api_settings_check():
        body = request.get_json(silent=True) or {}
        sources = body.get("sources") or ["netease", "bilibili"]
        cfg = _cfg()
        results = {}
        try:
            from tools.cookie_reply import test_cookie
        except Exception as e:
            return jsonify({"error": f"检测模块不可用：{e}"}), 500
        for source in sources:
            if source == "netease":
                value = (cfg.get("netease") or {}).get("cookie") or ""
                base = (cfg.get("netease") or {}).get("base_url") or "http://localhost:3000"
            elif source == "bilibili":
                value = (cfg.get("bilibili") or {}).get("sessdata") or ""
                base = ""
            else:
                continue
            if not value:
                results[source] = {"ok": False, "detail": "未配置"}
                continue
            try:
                ok, detail = test_cookie(source, value, base)
            except Exception as e:
                ok, detail = False, f"检测失败：{e}"
            results[source] = {"ok": bool(ok), "detail": detail}
        return jsonify({"results": results})

    # -- apply ignore lists to history + today, then republish ---------------
    _purge_state = {
        "running": False,
        "done": False,
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
    }
    _purge_lock = threading.Lock()

    def _run_purge():
        with _purge_lock:
            _purge_state.update(
                running=True, done=False,
                started_at=datetime.datetime.now().isoformat(timespec="seconds"),
                error=None)
        try:
            from tools.purge_ignored import purge_and_publish
            from .git_publish import commit_and_push_settings
            result = purge_and_publish()
            result["settings_publish"] = commit_and_push_settings(PROJECT_DIR)
            with _purge_lock:
                _purge_state["result"] = result
        except Exception as e:
            with _purge_lock:
                _purge_state["error"] = str(e)
        finally:
            with _purge_lock:
                _purge_state["running"] = False
                _purge_state["done"] = True
                _purge_state["finished_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            _heavy_lock.release()

    @app.route("/api/settings/purge", methods=["POST"])
    def api_settings_purge():
        if not _heavy_lock.acquire(blocking=False):
            return jsonify({"error": "另一个任务正在运行，请稍后再试"}), 429
        threading.Thread(target=_run_purge, daemon=True).start()
        return jsonify({"status": "started"})

    @app.route("/api/settings/purge/status")
    def api_settings_purge_status():
        with _purge_lock:
            return jsonify(dict(_purge_state))

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False, threaded=True)
