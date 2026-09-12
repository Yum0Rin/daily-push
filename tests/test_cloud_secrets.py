"""cloud_secrets: local -> cloud gh secret set (no real gh calls)."""
import unittest
from unittest import mock

from daily_push import cloud_secrets as cs


class _Fake:
    def __init__(self, rc=0, out="", err=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = err


class SyncCookiesTest(unittest.TestCase):
    def test_sync_uses_stdin_not_argv(self):
        calls = []

        def fake_run(args, timeout=60, env=None, input=None):
            calls.append({"args": args, "env": env, "input": input})
            return _Fake(0)

        with mock.patch.object(cs, "_run", fake_run):
            res = cs.sync_cookies({"site": {"repo": "u/r"}},
                                  {"netease": "MUSIC_U=abc", "bilibili": "sess"})
        self.assertTrue(res["netease"]["ok"])
        self.assertTrue(res["bilibili"]["ok"])
        self.assertEqual(calls[0]["args"][:3], ["gh", "secret", "set"])
        self.assertIn("NETEASE_COOKIE", calls[0]["args"])
        self.assertEqual(calls[0]["input"], "MUSIC_U=abc")          # value via stdin
        self.assertNotIn("MUSIC_U=abc", " ".join(calls[0]["args"]))  # not in argv
        self.assertEqual(calls[1]["args"][calls[1]["args"].index("--repo") + 1], "u/r")

    def test_token_passed_as_env(self):
        seen = {}

        def fake_run(args, timeout=60, env=None, input=None):
            seen["env"] = env
            return _Fake(0)

        with mock.patch.object(cs, "_run", fake_run):
            cs.sync_cookies({"site": {"repo": "u/r"}, "github": {"token": "PAT"}},
                            {"bilibili": "s"})
        self.assertEqual(seen["env"], {"GH_TOKEN": "PAT"})

    def test_missing_repo_fails_without_calling_gh(self):
        def boom(*a, **k):
            raise AssertionError("gh must not be called")

        with mock.patch.object(cs, "_run", boom):
            res = cs.sync_cookies({"site": {}}, {"bilibili": "s"})
        self.assertFalse(res["bilibili"]["ok"])
        self.assertIn("site.repo", res["bilibili"]["detail"])

    def test_gh_error_is_reported(self):
        with mock.patch.object(cs, "_run", lambda *a, **k: _Fake(1, err="HTTP 403")):
            res = cs.sync_cookies({"site": {"repo": "u/r"}}, {"bilibili": "s"})
        self.assertFalse(res["bilibili"]["ok"])
        self.assertIn("403", res["bilibili"]["detail"])


class AuthStatusTest(unittest.TestCase):
    def test_no_gh(self):
        with mock.patch.object(cs.shutil, "which", return_value=None):
            ok, detail = cs.gh_auth_status()
        self.assertFalse(ok)
        self.assertIn("gh", detail)

    def test_cloud_status_unavailable_without_repo(self):
        with mock.patch.object(cs, "gh_auth_status", return_value=(True, "gh 已登录")):
            st = cs.cloud_status({"site": {}})
        self.assertFalse(st["available"])
        self.assertIn("site.repo", st["detail"])


if __name__ == "__main__":
    unittest.main()
