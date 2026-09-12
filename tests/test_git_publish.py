"""git_publish must commit ONLY settings.json (never other files) and push."""
import json
import os
import subprocess
import tempfile
import unittest

from daily_push.git_publish import commit_and_push_settings


def git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


class GitPublishTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.repo = os.path.join(self.dir, "repo")
        self.remote = os.path.join(self.dir, "remote.git")
        os.makedirs(self.repo)
        git(["init", "-b", "main"], self.repo)
        git(["config", "user.email", "t@example.com"], self.repo)
        git(["config", "user.name", "tester"], self.repo)
        self._write("settings.json", json.dumps({"max_songs": 5}))
        self._write("foo.txt", "a")
        git(["add", "-A"], self.repo)
        git(["commit", "-m", "init"], self.repo)
        subprocess.run(["git", "init", "--bare", self.remote], capture_output=True)
        git(["remote", "add", "origin", self.remote], self.repo)
        git(["push", "-u", "origin", "main"], self.repo)

    def _write(self, name, text):
        with open(os.path.join(self.repo, name), "w", encoding="utf-8") as f:
            f.write(text)

    def test_commits_only_settings_and_pushes(self):
        self._write("settings.json", json.dumps({"max_songs": 9}))
        self._write("foo.txt", "b")  # unrelated dirty file
        res = commit_and_push_settings(self.repo, remote="origin", branch="main")
        self.assertTrue(res["committed"])
        self.assertTrue(res["pushed"])

        remote_settings = subprocess.run(
            ["git", "--git-dir", self.remote, "show", "main:settings.json"],
            capture_output=True, text=True, encoding="utf-8")
        self.assertIn('"max_songs": 9', remote_settings.stdout)

        remote_foo = subprocess.run(
            ["git", "--git-dir", self.remote, "show", "main:foo.txt"],
            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(remote_foo.stdout.strip(), "a")  # not committed

        local_status = git(["status", "--porcelain"], self.repo).stdout
        self.assertIn("foo.txt", local_status)  # still dirty locally

    def test_no_change_is_skipped(self):
        res = commit_and_push_settings(self.repo, remote="origin", branch="main")
        self.assertFalse(res["committed"])
        self.assertFalse(res["pushed"])
        self.assertIn("无变化", res["detail"])


if __name__ == "__main__":
    unittest.main()
