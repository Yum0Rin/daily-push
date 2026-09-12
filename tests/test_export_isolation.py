"""The exported public site must never contain settings UI or credentials."""
import json
import os
import tempfile
import unittest

from daily_push.export_site import export_site


class ExportIsolationTest(unittest.TestCase):
    def test_export_has_no_settings_or_token(self):
        d = tempfile.mkdtemp()
        cfg_path = os.path.join(d, "config.json")
        site_dir = os.path.join(d, "site")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump({
                "data_dir": d,
                "site": {"export_dir": site_dir, "repo": "", "branch": "main"},
            }, f)
        path = export_site(cfg_path, merge_remote=False)
        with open(path, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("window.__DAYS__", html)
        self.assertNotIn('id="settingsLink"', html)
        self.assertNotIn('href="/settings"', html)
        self.assertNotIn("csrf-token", html)


if __name__ == "__main__":
    unittest.main()
