"""purge_and_publish must clean remote-only days too (merge BEFORE purge)."""
import json
import os
import tempfile
import unittest
from unittest import mock

from daily_push import export_site as es
from daily_push import settings_store as ss
from daily_push.storage import Storage
from tools.purge_ignored import purge_and_publish


class PurgeOrderTest(unittest.TestCase):
    def test_remote_only_day_is_purged_not_republished(self):
        d = tempfile.mkdtemp()
        cfg_path = os.path.join(d, "config.json")
        settings_path = os.path.join(d, "settings.json")
        site_dir = os.path.join(d, "site")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump({"data_dir": d,
                       "site": {"export_dir": site_dir, "repo": "", "branch": "main"}}, f)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump({"wechat": {"exclude_keywords": ["Bad"]}}, f)

        remote = {"2026-01-01": {"mp": [{"author": "Bad号", "title": "x"}],
                                 "bilibili": [], "netease": None}}
        with mock.patch.object(es, "_published_days_from_remote", return_value=remote), \
                mock.patch.object(ss, "SETTINGS_PATH", settings_path):
            purge_and_publish(config_path=cfg_path)

        st = Storage(d)
        row = st.get("2026-01-01")
        st.close()
        self.assertIsNotNone(row)          # day was merged in
        self.assertFalse(row.get("mp"))    # ...and then purged

        with open(os.path.join(site_dir, "index.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertNotIn("Bad号", html)


if __name__ == "__main__":
    unittest.main()
