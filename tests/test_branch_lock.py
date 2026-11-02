"""branch_lock: the pre-commit hook keeps task commits off the live checkout and lets the sync through."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "branch_lock.py"
ENV = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "SYNC_COMMIT"))}


def git(cwd, *args, env=None, check=True):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
                       cwd=cwd, capture_output=True, text=True, env=env or ENV)
    if check and r.returncode != 0:
        raise AssertionError(f"git {args}: {r.stderr}")
    return r


def install(repo):
    return subprocess.run([sys.executable, "-I", str(TOOL), "install", str(repo)], capture_output=True, text=True)


class BranchLockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.work = t / "work"
        git(t, "init", "-q", "--bare", "-b", "main", str(t / "remote.git"))
        git(t, "clone", "-q", str(t / "remote.git"), str(self.work))
        git(self.work, "checkout", "-q", "-B", "main")
        self.commit("a")
        git(self.work, "push", "-q", "origin", "main")
        git(self.work, "remote", "set-head", "origin", "main")
        self.assertEqual(install(self.work).returncode, 0)

    def commit(self, name, env=None, check=True):
        (self.work / name).write_text(name + "\n", encoding="utf-8")
        git(self.work, "add", "-A")
        return git(self.work, "commit", "-q", "-m", name, env=env, check=check)

    def test_commit_on_the_default_branch_passes(self):
        self.assertEqual(self.commit("b").returncode, 0)

    def test_commit_on_another_branch_is_refused_with_the_worktree_command(self):
        git(self.work, "switch", "-q", "-c", "codex/task")
        r = self.commit("b", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("codex/task", r.stderr)
        self.assertIn("git worktree add ~/Codes/.worktrees/<name> -b <branch> origin/main", r.stderr)

    def test_sync_commit_passes_on_another_branch(self):
        git(self.work, "switch", "-q", "-c", "codex/task")
        self.assertEqual(self.commit("b", env={**ENV, "SYNC_COMMIT": "1"}).returncode, 0)

    def test_a_linked_worktree_may_commit_on_its_branch(self):
        wt = Path(self.tmp.name) / "wt"
        git(self.work, "worktree", "add", "-q", str(wt), "-b", "feat", "origin/main")
        (wt / "x").write_text("x\n", encoding="utf-8")
        git(wt, "add", "-A")
        self.assertEqual(git(wt, "commit", "-q", "-m", "x").returncode, 0)

    def test_install_is_idempotent_and_chains_an_existing_pre_commit_hook(self):
        self.assertIn("already installed", install(self.work).stdout)
        hook = self.work / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\necho ran-mine >&2\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        self.assertEqual(install(self.work).returncode, 0)
        r = self.commit("b", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ran-mine", r.stderr)  # the existing hook still runs, after the lock

    def test_install_follows_core_hooks_path_and_keeps_the_pre_push_hook(self):
        pre_push = self.work / ".git" / "hooks" / "pre-push"
        pre_push.write_text("#!/bin/sh\n", encoding="utf-8")
        shared = Path(self.tmp.name) / "shared-hooks"
        git(self.work, "config", "core.hooksPath", str(shared))
        self.assertEqual(install(self.work).returncode, 0)
        self.assertTrue((shared / "pre-commit").exists())
        git(self.work, "switch", "-q", "-c", "codex/task")
        self.assertNotEqual(self.commit("b", check=False).returncode, 0)
        self.assertEqual(pre_push.read_text(encoding="utf-8"), "#!/bin/sh\n")

    def test_sync_scripts_commit_with_the_sync_marker_and_install_the_lock(self):
        sync = (ROOT / "sync.sh").read_text(encoding="utf-8")
        self.assertIn('branch_lock.py" install "$DST"', sync)
        self.assertIn("SYNC_COMMIT=1 git commit", sync)
        self.assertIn("SYNC_COMMIT=1 git commit", (ROOT / "weekly.sh").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
