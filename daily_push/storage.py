"""SQLite storage layer for daily pushes."""
import json
import os
import sqlite3
import threading
from datetime import date

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pushes (
    push_date   TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    netease     TEXT,
    bilibili    TEXT,
    qq          TEXT,
    wechat      TEXT,
    mp          TEXT
);
"""


class Storage:
    def __init__(self, data_dir="data"):
        os.makedirs(data_dir, exist_ok=True)
        self.conn = sqlite3.connect(os.path.join(data_dir, "daily.db"), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self.conn.execute(_SCHEMA)
            cols = [r[1] for r in self.conn.execute("PRAGMA table_info(pushes)").fetchall()]
            if "mp" not in cols:
                self.conn.execute("ALTER TABLE pushes ADD COLUMN mp TEXT")
            self.conn.commit()

    @staticmethod
    def _has_data(v):
        if v is None:
            return False
        if isinstance(v, dict) and "error" in v:
            return False
        if isinstance(v, list):
            return bool(v)
        return True

    def save(self, push_date, netease=None, bilibili=None, qq=None, wechat=None, mp=None):
        import datetime
        now = datetime.datetime.now().isoformat(timespec="seconds")
        fields = {"netease": netease, "bilibili": bilibili,
                  "qq": qq, "wechat": wechat, "mp": mp}
        with self._lock:
            existing = self.conn.execute(
                "SELECT netease, bilibili, qq, wechat, mp FROM pushes WHERE push_date=?",
                (push_date,)).fetchone()
            merged = {}
            for name, val in fields.items():
                if existing is not None and not self._has_data(val):
                    old = json.loads(existing[name]) if existing[name] else None
                    if self._has_data(old):
                        val = old
                merged[name] = val
            self.conn.execute(
                "INSERT INTO pushes (push_date, created_at, netease, bilibili, qq, wechat, mp) "
                "VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(push_date) DO UPDATE SET "
                "created_at=excluded.created_at, netease=excluded.netease, "
                "bilibili=excluded.bilibili, qq=excluded.qq, wechat=excluded.wechat, "
                "mp=excluded.mp",
                (push_date, now,
                 json.dumps(merged["netease"], ensure_ascii=False) if merged["netease"] is not None else None,
                 json.dumps(merged["bilibili"], ensure_ascii=False) if merged["bilibili"] is not None else None,
                 json.dumps(merged["qq"], ensure_ascii=False) if merged["qq"] is not None else None,
                 json.dumps(merged["wechat"], ensure_ascii=False) if merged["wechat"] is not None else None,
                 json.dumps(merged["mp"], ensure_ascii=False) if merged["mp"] is not None else None),
            )
            self.conn.commit()

    def get(self, push_date):
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM pushes WHERE push_date=?", (push_date,)).fetchone()
        if not row:
            return None
        return {
            "push_date": row["push_date"],
            "created_at": row["created_at"],
            "netease": json.loads(row["netease"]) if row["netease"] else None,
            "bilibili": json.loads(row["bilibili"]) if row["bilibili"] else None,
            "qq": json.loads(row["qq"]) if row["qq"] else None,
            "wechat": json.loads(row["wechat"]) if row["wechat"] else None,
            "mp": json.loads(row["mp"]) if row["mp"] else None,
        }

    def list_dates(self):
        with self._lock:
            rows = self.conn.execute(
                "SELECT push_date FROM pushes ORDER BY push_date DESC").fetchall()
        return [r["push_date"] for r in rows]

    def has(self, push_date):
        return self.get(push_date) is not None

    def pushed_urls(self, field, exclude_date=None):
        """Return set of urls already pushed for `field` in past days."""
        field = str(field)
        with self._lock:
            rows = self.conn.execute(
                f"SELECT push_date, {field} FROM pushes WHERE {field} IS NOT NULL"
            ).fetchall()
        urls = set()
        for pd, raw in rows:
            if exclude_date and pd == exclude_date:
                continue
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if isinstance(data, list):
                for it in data:
                    if not isinstance(it, dict):
                        continue
                    url = it.get("url")
                    if not url and isinstance(it.get("latest"), dict):
                        url = it["latest"].get("url")
                    if url:
                        urls.add(url)
        return urls

    def close(self):
        self.conn.close()