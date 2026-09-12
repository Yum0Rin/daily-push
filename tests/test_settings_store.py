"""Tests for the layered settings store (no network, stdlib unittest)."""
import json
import os
import tempfile
import unittest

from daily_push import settings_store as ss


def _write(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


class LayeredLoadTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.config = os.path.join(self.dir, "config.json")
        self.settings = os.path.join(self.dir, "settings.json")

    def test_policy_overrides_stale_config_and_secrets_survive(self):
        _write(self.config, {
            "netease": {"mode": "api", "cookie": "MUSIC_U=SECRET", "base_url": "http://localhost:3000"},
            "bilibili": {"sessdata": "SESS", "exclude": ["stale"], "recent_days": 9},
            "max_songs": 3,
        })
        _write(self.settings, {
            "bilibili": {"exclude": ["fresh"], "recent_days": 1},
            "max_songs": 5,
        })
        cfg = ss.load_config(self.config, self.settings)
        self.assertEqual(cfg["bilibili"]["exclude"], ["fresh"])
        self.assertEqual(cfg["bilibili"]["recent_days"], 1)
        self.assertEqual(cfg["max_songs"], 5)
        self.assertEqual(cfg["bilibili"]["sessdata"], "SESS")
        self.assertEqual(cfg["netease"]["cookie"], "MUSIC_U=SECRET")

    def test_secret_keys_in_settings_are_ignored(self):
        _write(self.config, {"netease": {"cookie": "MUSIC_U=REAL"}})
        _write(self.settings, {
            "netease": {"cookie": "MUSIC_U=EVIL"},
            "bilibili": {"sessdata": "EVIL"},
            "push_time": "06:00",
        })
        cfg = ss.load_config(self.config, self.settings)
        self.assertEqual(cfg["netease"]["cookie"], "MUSIC_U=REAL")
        self.assertIsNone((cfg.get("bilibili") or {}).get("sessdata"))
        self.assertEqual(cfg["push_time"], "06:00")

    def test_missing_settings_file_is_fine(self):
        _write(self.config, {"max_songs": 4})
        cfg = ss.load_config(self.config, os.path.join(self.dir, "nope.json"))
        self.assertEqual(cfg["max_songs"], 4)
        self.assertEqual(cfg["netease"]["mode"], "api")  # default applied


class SaveTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.config = os.path.join(self.dir, "config.json")
        self.settings = os.path.join(self.dir, "settings.json")

    def test_save_policy_validates_and_writes(self):
        ss.save_policy({"bilibili": {"exclude": ["a", "a", " ", "b"]}}, self.settings)
        with open(self.settings, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["bilibili"]["exclude"], ["a", "b"])

    def test_save_policy_rejects_unknown_and_bad_type(self):
        with self.assertRaises(ss.SettingsError):
            ss.save_policy({"bilibili": {"nope": 1}}, self.settings)
        with self.assertRaises(ss.SettingsError):
            ss.save_policy({"max_songs": 999}, self.settings)
        with self.assertRaises(ss.SettingsError):
            ss.save_policy({"push_time": "25:99"}, self.settings)

    def test_save_secrets_backs_up_and_preserves_unknown_keys(self):
        _write(self.config, {"netease": {"cookie": "OLD"}, "xiaohongshu": {"limit": 5}})
        ss.save_secrets({"netease": {"cookie": "MUSIC_U=NEW"}}, self.config)
        with open(self.config, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["netease"]["cookie"], "MUSIC_U=NEW")
        self.assertEqual(data["xiaohongshu"]["limit"], 5)
        self.assertTrue(os.path.exists(self.config + ".bak"))
        with open(self.config + ".bak", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["netease"]["cookie"], "OLD")

    def test_save_secrets_rejects_unknown_key(self):
        with self.assertRaises(ss.SettingsError):
            ss.save_secrets({"netease": {"hax": "1"}}, self.config)


class ViewTest(unittest.TestCase):
    def test_mask_hides_middle(self):
        self.assertEqual(ss.mask(""), "")
        self.assertEqual(ss.mask("short"), "•••••")
        m = ss.mask("MUSIC_U=ABCDEFGHIJK")
        self.assertIn("••••••", m)
        self.assertNotIn("EFGH", m)

    def test_secrets_view_never_returns_raw(self):
        d = tempfile.mkdtemp()
        cfg = os.path.join(d, "config.json")
        _write(cfg, {"netease": {"cookie": "MUSIC_U=ABCDEFGHIJK"},
                     "bilibili": {"sessdata": "SESSDATAVALUE"}})
        view = ss.secrets_view(cfg)
        blob = json.dumps(view, ensure_ascii=False)
        self.assertNotIn("ABCDEFGHIJK", blob)
        self.assertNotIn("SESSDATAVALUE", blob)
        self.assertTrue(view["netease"]["cookie_configured"])
        self.assertTrue(view["bilibili"]["sessdata_configured"])


if __name__ == "__main__":
    unittest.main()
