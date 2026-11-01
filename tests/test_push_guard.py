"""push_guard: the pre-push hook refuses deleting or force-pushing main and lets a fast-forward through."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "push_guard.py"
ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and not k.startswith("PUSH_GUARD")}


def git(cwd, *args, env=None, check=True):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd,
                       capture_output=True, text=True, env=env or ENV)
    if check and r.returncode != 0:
        raise AssertionError(f"git {args}: {r.stderr}")
    return r


def commit(repo, name):
    (Path(repo) / name).write_text(name + "\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", name)


class PushGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.remote = t / "remote.git"
        self.work = t / "work"
        git(t, "init", "-q", "--bare", "-b", "main", str(self.remote))
        git(t, "clone", "-q", str(self.remote), str(self.work))
        git(self.work, "checkout", "-q", "-B", "main")
        commit(self.work, "a")
        git(self.work, "push", "-q", "origin", "main")  # before the hook: seed the remote
        r = subprocess.run([sys.executable, "-I", str(TOOL), "install", str(self.work)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        self.tmp.cleanup()

    def push(self, *args, env=None):
        e = dict(ENV)
        e.update(env or {})
        return git(self.work, "push", *args, env=e, check=False)

    def test_fast_forward_passes(self):
        commit(self.work, "b")
        self.assertEqual(self.push("origin", "main").returncode, 0)

    def test_force_push_of_a_rewritten_main_is_refused(self):
        commit(self.work, "b")
        self.assertEqual(self.push("origin", "main").returncode, 0)
        git(self.work, "reset", "-q", "--hard", "HEAD~1")
        commit(self.work, "c")
        r = self.push("--force", "origin", "main")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("non-fast-forward", r.stderr)

    def test_deleting_main_is_refused(self):
        r = self.push("origin", "--delete", "main")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("deleting main", r.stderr)

    def test_other_branches_may_be_forced_and_deleted(self):
        git(self.work, "checkout", "-q", "-b", "topic")
        commit(self.work, "t1")
        self.assertEqual(self.push("origin", "topic").returncode, 0)
        git(self.work, "reset", "-q", "--hard", "HEAD~1")
        commit(self.work, "t2")
        self.assertEqual(self.push("--force", "origin", "topic").returncode, 0)
        self.assertEqual(self.push("origin", "--delete", "topic").returncode, 0)

    def test_allow_variable_lets_a_deliberate_rewrite_through(self):
        git(self.work, "commit", "-q", "--amend", "-m", "a2")
        self.assertNotEqual(self.push("--force", "origin", "main").returncode, 0)
        r = self.push("--force", "origin", "main", env={"PUSH_GUARD_ALLOW": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PUSH_GUARD_ALLOW=1", r.stderr)

    def test_protected_branches_come_from_the_environment(self):
        git(self.work, "checkout", "-q", "-b", "release")
        commit(self.work, "r1")
        self.assertEqual(self.push("origin", "release").returncode, 0)
        r = self.push("origin", "--delete", "release", env={"PUSH_GUARD_BRANCHES": "main,release"})
        self.assertNotEqual(r.returncode, 0)

    def test_install_is_idempotent_and_keeps_a_foreign_hook(self):
        again = subprocess.run([sys.executable, "-I", str(TOOL), "install", str(self.work)], capture_output=True, text=True)
        self.assertIn("already installed", again.stdout)
        hook = self.work / ".git" / "hooks" / "pre-push"
        hook.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
        r = subprocess.run([sys.executable, "-I", str(TOOL), "install", str(self.work)], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(hook.read_text(encoding="utf-8"), "#!/bin/sh\necho mine\n")

    def test_unknown_remote_tip_is_refused(self):
        v = subprocess.run([sys.executable, "-I", str(TOOL), "check", "origin", "x"], capture_output=True, text=True,
                           input="refs/heads/main " + "1" * 40 + " refs/heads/main " + "2" * 40 + "\n", cwd=self.work, env=ENV)
        self.assertNotEqual(v.returncode, 0)
        self.assertIn("git fetch first", v.stderr)


if __name__ == "__main__":
    unittest.main()
