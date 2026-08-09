"""Flask web app: serve the daily dashboard + history browsing + trigger collect."""
import datetime
import os
import threading

from flask import Flask, jsonify, render_template, request

from .config import load_config
from .collector import collect_once
from .storage import Storage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)


def create_app(config_path=None):
    cfg = load_config(config_path)
    storage = Storage(os.path.join(PROJECT_DIR, cfg.get("data_dir", "data")))

    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/dates")
    def dates():
        return jsonify({"dates": storage.list_dates()})

    @app.route("/api/today")
    def today():
        return jsonify(storage.get(datetime.date.today().isoformat()) or {"push_date": datetime.date.today().isoformat()})

    @app.route("/api/day/<date_str>")
    def day(date_str):
        return jsonify(storage.get(date_str) or {"error": "no data", "push_date": date_str})

    _lock = threading.Lock()
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

    @app.route("/api/collect", methods=["POST"])
    def trigger_collect():
        if not _lock.acquire(blocking=False):
            return jsonify({"error": "already running"}), 429
        try:
            t = threading.Thread(target=_run_collect, daemon=True)
            t.start()
            return jsonify({"status": "started"})
        finally:
            _lock.release()

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
        today = storage.get(datetime.date.today().isoformat())
        return jsonify({
            "today_pushed": bool(today),
            "history_days": len(storage.list_dates()),
            "config": {
                "push_time": cfg.get("push_time", "08:30"),
                "bilibili_configured": bool(cfg.get("bilibili", {}).get("sessdata")),
                "netease_configured": bool(cfg.get("netease", {}).get("cookie")),
            },
        })

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False, threaded=True)