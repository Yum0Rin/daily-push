"""API-level tests for the local settings page and its guards."""
import json
import os
import tempfile
import unittest

from daily_push.app import create_app


def _write(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


class SettingsApiTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.config = os.path.join(self.dir, "config.json")
        self.settings = os.path.join(self.dir, "settings.json")
        _write(self.config, {
            "netease": {"mode": "api", "cookie": "MUSIC_U=ABCDEFGHIJK",
                        "base_url": "http://localhost:3000"},
            "bilibili": {"sessdata": "SESSDATAVALUE"},
            "data_dir": self.dir,
        })
        _write(self.settings, {"bilibili": {"exclude": ["old"]}, "max_songs": 5})
        app = create_app(self.config, self.settings)
        app.config["TESTING"] = True
        self.token = app.config["SETTINGS_TOKEN"]
        self.client = app.test_client()

    def _h(self, origin=None):
        h = {"X-CSRF-Token": self.token}
        if origin:
            h["Origin"] = origin
        return h

    def test_settings_page_renders_with_token(self):
        r = self.client.get("/settings")
        self.assertEqual(r.status_code, 200)
        self.assertIn("csrf-token", r.get_data(as_text=True))

    def test_get_api_requires_token(self):
        self.assertEqual(self.client.get("/api/settings").status_code, 403)
        r = self.client.get("/api/settings", headers=self._h())
        self.assertEqual(r.status_code, 200)

    def test_get_api_never_leaks_raw_secret(self):
        r = self.client.get("/api/settings", headers=self._h())
        body = r.get_data(as_text=True)
        self.assertNotIn("ABCDEFGHIJK", body)
        self.assertNotIn("SESSDATAVALUE", body)

    def test_policy_save_and_reload(self):
        r = self.client.post("/api/settings/policy",
                             json={"policy": {"bilibili": {"exclude": ["new"]}}},
                             headers=self._h())
        self.assertEqual(r.status_code, 200)
        with open(self.settings, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["bilibili"]["exclude"], ["new"])

    def test_policy_rejects_unknown_key(self):
        r = self.client.post("/api/settings/policy",
                             json={"policy": {"bilibili": {"nope": 1}}},
                             headers=self._h())
        self.assertEqual(r.status_code, 400)

    def test_secrets_save_masks_response(self):
        r = self.client.post("/api/settings/secrets",
                             json={"secrets": {"bilibili": "NEWSESSDATATOKEN1"}},
                             headers=self._h())
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("NEWSESSDATATOKEN1", r.get_data(as_text=True))
        with open(self.config, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["bilibili"]["sessdata"], "NEWSESSDATATOKEN1")

    def test_bad_origin_rejected(self):
        r = self.client.post("/api/settings/policy",
                             json={"policy": {"max_songs": 6}},
                             headers=self._h(origin="http://evil.example"))
        self.assertEqual(r.status_code, 403)

    def test_bad_host_rejected(self):
        r = self.client.get("/api/settings", headers=self._h(),
                            base_url="http://evil.example")
        self.assertEqual(r.status_code, 403)

    def test_cloud_endpoints_require_token(self):
        self.assertEqual(self.client.get("/api/settings/cloud-status").status_code, 403)
        self.assertEqual(
            self.client.post("/api/settings/sync-cloud",
                             json={"sources": ["bilibili"]}).status_code, 403)

    def test_sync_cloud_without_repo_reports_error(self):
        r = self.client.post("/api/settings/sync-cloud",
                             json={"sources": ["bilibili"]}, headers=self._h())
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["results"]["bilibili"]["ok"])

    def test_security_headers(self):
        r = self.client.get("/settings")
        self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(r.headers.get("X-Frame-Options"), "DENY")
        self.assertIn("Content-Security-Policy", r.headers)

    def test_settings_get_includes_status(self):
        r = self.client.get("/api/settings", headers=self._h())
        self.assertIn("status", r.get_json())

    def test_config_backup_and_restore(self):
        r = self.client.get("/api/settings/config-backup", headers=self._h())
        self.assertEqual(r.status_code, 200)
        self.assertIn("netease", r.get_json()["config"])
        r2 = self.client.post("/api/settings/config-restore",
                              json={"config": {"netease": {"cookie": "MUSIC_U=NEWVALUE"}}},
                              headers=self._h())
        self.assertEqual(r2.status_code, 200)
        with open(self.config, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["netease"]["cookie"], "MUSIC_U=NEWVALUE")

    def test_config_restore_requires_token(self):
        r = self.client.post("/api/settings/config-restore", json={"config": {}})
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
