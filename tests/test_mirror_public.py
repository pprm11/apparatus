"""Offline tests for tools/mirror_public.py: the public-mirror step (deny scan, file list, copy, local publish)
and its wiring in sync.sh. Run: python -I -m unittest discover -s tests"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TOOL = os.path.join(ROOT, "tools", "mirror_public.py")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mirror_public as mp  # noqa: E402
from test_shell_sync import BASH  # noqa: E402

# One deny pattern is enough: the tool must reuse the gate's scan, not its own list.
CONFIG = {
    "denylist": {
        "allow_paths": ["ci/*"],
        "patterns": [{"name": "owner-name", "regex": "\\bgrace"}],
    }
}
LEAK = "written by Grace"  # matches owner-name (case-insensitive, like the gate)


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


class MirrorBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mirror-public-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = os.path.join(self.tmp, "src")
        self.dst = os.path.join(self.tmp, "mirror")
        self.env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                        GIT_COMMITTER_EMAIL="t@t", GIT_CONFIG_NOSYSTEM="1", PYTHONIOENCODING="utf-8")
        self.git(self.tmp, "init", "-q", "-b", "main", self.src)
        write(os.path.join(self.src, "ci", "config.json"), json.dumps(CONFIG))
        write(os.path.join(self.src, "README.md"), "generic text\n")
        write(os.path.join(self.src, "skills", "demo", "SKILL.md"), "skill\n")
        write(os.path.join(self.src, "runs", "r1", "log.txt"), "tracked by mistake\n")
        write(os.path.join(self.src, "lint-report.md"), "generated\n")
        write(os.path.join(self.src, "ci", "deny-baseline.txt"), "# header\n")
        write(os.path.join(self.src, "ci", "gates.py"), "print(1)\n")
        write(os.path.join(self.src, "ci", "privacy-terms.json"), json.dumps({
            "patterns": [{"name": "email", "regex": "example-pattern"}],
            "forbidden_layer_repos": [], "personal_levels": ["id"],
        }))

    def commit(self):
        self.git(self.src, "add", "-A", "-f")
        self.git(self.src, "commit", "-qm", "c")

    def git(self, cwd, *args):
        r = subprocess.run(["git", *args], cwd=cwd, env=self.env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def run_tool(self, *args, env=None):
        return subprocess.run([sys.executable, "-I", TOOL, "--source", self.src, *args], env=env or self.env,
                              capture_output=True, text=True, encoding="utf-8")


class PlanTest(MirrorBase):
    def test_lists_tracked_files_without_the_excluded_ones(self):
        self.commit()
        plan = mp.make_plan(self.src)
        self.assertEqual(plan.hits, [])
        self.assertEqual(plan.files, ["README.md", "ci/privacy-terms.json", "skills/demo/SKILL.md"])

    def test_a_deny_hit_is_reported_with_file_and_pattern_name_only(self):
        write(os.path.join(self.src, "docs", "a.md"), LEAK + "\n")
        self.commit()
        plan = mp.make_plan(self.src)
        self.assertEqual(plan.hits, [("docs/a.md", "owner-name")])

    def test_a_private_name_in_runtime_privacy_terms_refuses_the_mirror(self):
        write(os.path.join(self.src, "ci", "privacy-terms.json"), LEAK + "\n")
        self.commit()
        plan = mp.make_plan(self.src)
        self.assertEqual(plan.hits, [("ci/privacy-terms.json", "owner-name")])
        r = self.run_tool("--target", self.dst)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self.dst))

    def test_unknown_ci_files_and_staged_private_terms_are_excluded(self):
        write(os.path.join(self.src, "ci", "future-config.json"), LEAK)
        write(os.path.join(self.src, ".staging", "privacy-terms.local.json"), LEAK)
        self.commit()
        plan = mp.make_plan(self.src)
        self.assertEqual(plan.hits, [])
        self.assertNotIn("ci/future-config.json", plan.files)
        self.assertNotIn(".staging/privacy-terms.local.json", plan.files)

    def test_reads_the_committed_content_not_the_working_tree(self):
        self.commit()
        write(os.path.join(self.src, "README.md"), LEAK + "\n")  # uncommitted edit
        self.assertEqual(mp.make_plan(self.src).hits, [])


class CliTest(MirrorBase):
    def test_dry_run_lists_files_and_writes_nothing(self):
        self.commit()
        r = self.run_tool("--dry-run", "--target", self.dst)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("would publish 3 file(s)", r.stdout)
        self.assertIn("ci/privacy-terms.json", r.stdout)
        self.assertIn("parent: none", r.stdout)
        self.assertIn("README.md", r.stdout)
        self.assertNotIn("runs/r1/log.txt", r.stdout)
        self.assertFalse(os.path.exists(self.dst))

    def test_refuses_on_a_deny_hit_and_never_prints_the_matched_text(self):
        write(os.path.join(self.src, "docs", "a.md"), LEAK + "\n")
        self.commit()
        for args in (["--dry-run"], ["--target", self.dst]):
            r = self.run_tool(*args, "--target", self.dst) if args == ["--dry-run"] else self.run_tool(*args)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("REFUSED", r.stderr)
            self.assertIn("docs/a.md owner-name", r.stderr)
            self.assertNotIn("Grace", r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self.dst))

    def test_builds_the_tree_with_the_mirror_notice(self):
        self.commit()
        head = self.git(self.src, "rev-parse", "HEAD")
        r = self.run_tool("--target", self.dst)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.dst, "MIRROR.md"), encoding="utf-8") as fh:
            notice = fh.read()
        self.assertIn(head, notice)
        self.assertIn("no source history", notice)
        self.assertIn("git pull --ff-only", notice)
        self.assertIn("accepts no pull requests", notice)
        self.assertTrue(os.path.isfile(os.path.join(self.dst, "skills", "demo", "SKILL.md")))
        self.assertFalse(os.path.exists(os.path.join(self.dst, "runs")))
        self.assertFalse(os.path.exists(os.path.join(self.dst, "lint-report.md")))
        self.assertFalse(os.path.exists(os.path.join(self.dst, "ci", "deny-baseline.txt")))

    def test_a_rebuild_drops_files_that_left_the_source(self):
        self.commit()
        self.assertEqual(self.run_tool("--target", self.dst).returncode, 0)
        self.git(self.src, "rm", "-q", "README.md")
        self.git(self.src, "commit", "-qm", "rm")
        self.assertEqual(self.run_tool("--target", self.dst).returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.dst, "README.md")))

    def test_refuses_to_wipe_a_folder_that_is_not_a_mirror(self):
        self.commit()
        write(os.path.join(self.dst, "precious.txt"), "keep\n")
        r = self.run_tool("--target", self.dst)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.dst, "precious.txt")))

    def test_publish_appends_one_parent_and_a_clone_fast_forwards(self):
        self.commit()
        remote = os.path.join(self.tmp, "public.git")
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", remote)
        r = self.run_tool("--target", self.dst, "--publish", "--remote", remote)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        first = self.git(remote, "rev-parse", "main")
        self.assertEqual(self.git(remote, "rev-list", "--count", "main"), "1")
        clone = os.path.join(self.tmp, "client")
        self.git(self.tmp, "clone", "-q", remote, clone)
        write(os.path.join(self.src, "README.md"), "updated generic text\n")
        self.commit()
        dry = self.run_tool("--dry-run", "--remote", remote)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn(f"parent: {first}", dry.stdout)
        # A fresh target must fetch the parent from the remote, rather than reuse local history.
        r = self.run_tool("--target", self.dst + "-fresh", "--publish", "--remote", remote)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        second = self.git(remote, "rev-parse", "main")
        self.assertEqual(self.git(remote, "rev-list", "--parents", "-n", "1", "main"), f"{second} {first}")
        self.assertEqual(self.git(remote, "rev-list", "--count", "main"), "2")
        self.git(clone, "pull", "--ff-only")
        self.assertEqual(self.git(clone, "rev-parse", "HEAD"), second)
        self.assertEqual(Path(clone, "README.md").read_text(encoding="utf-8"), "updated generic text\n")
        self.assertTrue(Path(clone, "ci", "privacy-terms.json").is_file())

    def test_publish_rejects_a_concurrent_remote_update(self):
        self.commit()
        remote = os.path.join(self.tmp, "public.git")
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", remote)
        r = self.run_tool("--target", self.dst, "--publish", "--remote", remote)
        self.assertEqual(r.returncode, 0, r.stderr)
        rival = os.path.join(self.tmp, "rival")
        self.git(self.tmp, "clone", "-q", remote, rival)
        plan = mp.make_plan(self.src)
        mp.build(self.src, self.dst, plan)
        original_git = mp.git
        pushed = []

        def race(root, *args, **kwargs):
            if args[0] == "push":
                self.assertNotIn("--force", args)
                write(os.path.join(rival, "rival.txt"), "concurrent publish\n")
                self.git(rival, "add", "-A")
                self.git(rival, "commit", "-qm", "rival")
                self.git(rival, "push", "-q", "origin", "main")
                pushed.append(self.git(remote, "rev-parse", "main"))
            return original_git(root, *args, **kwargs)

        with mock.patch.object(mp, "git", side_effect=race), self.assertRaises(OSError):
            mp.publish(self.dst, remote, plan)
        self.assertEqual(self.git(remote, "rev-parse", "main"), pushed[0])

    def test_dry_run_remote_failure_is_reported_without_building(self):
        self.commit()
        r = self.run_tool("--dry-run", "--remote", os.path.join(self.tmp, "missing.git"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self.dst))

    def test_publish_needs_a_remote(self):
        self.commit()
        r = self.run_tool("--target", self.dst, "--publish")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("--remote", r.stderr)


@unittest.skipUnless(BASH, "needs Git Bash")
class SyncStepTest(MirrorBase):
    """lib.sh public_mirror is the step sync.sh calls: off unless PUBLIC_MIRROR=1, deny scan before anything is
    written, a failure that sync.sh reports without aborting."""

    def step(self, **flags):
        lib = os.path.join(ROOT, "lib.sh").replace("\\", "/")
        root = ROOT.replace("\\", "/")
        src = self.src.replace("\\", "/")
        env = dict(self.env, **{k: v.replace("\\", "/") for k, v in flags.items()})
        return subprocess.run([BASH, "-c", f'. "{lib}"; public_mirror "{root}" "{src}"'], env=env,
                              capture_output=True, text=True, encoding="utf-8")

    def test_skipped_when_the_flag_is_off(self):
        write(os.path.join(self.src, "docs", "a.md"), LEAK + "\n")  # would be refused if the step ran
        self.commit()
        for flags in ({}, {"PUBLIC_MIRROR": "0", "PUBLIC_MIRROR_DIR": self.dst}):
            r = self.step(**flags)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(r.stdout + r.stderr, "")
        self.assertFalse(os.path.exists(self.dst))

    def test_refused_when_the_deny_scan_hits(self):
        write(os.path.join(self.src, "docs", "a.md"), LEAK + "\n")
        self.commit()
        r = self.step(PUBLIC_MIRROR="1", PUBLIC_MIRROR_DIR=self.dst)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("REFUSED", r.stderr)
        self.assertFalse(os.path.exists(self.dst))

    def test_builds_the_tree_when_on_and_clean(self):
        self.commit()
        r = self.step(PUBLIC_MIRROR="1", PUBLIC_MIRROR_DIR=self.dst)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.dst, "MIRROR.md")))

    def test_on_without_a_target_fails_loudly(self):
        r = self.step(PUBLIC_MIRROR="1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("PUBLIC_MIRROR_DIR", r.stderr)

    def test_sync_calls_the_step_and_a_failure_only_warns(self):
        with open(os.path.join(ROOT, "sync.sh"), encoding="utf-8") as fh:
            line = next(ln for ln in fh if "public_mirror " in ln)
        self.assertIn('public_mirror "$DST" "$DST" ||', line)
        self.assertIn("echo", line)


if __name__ == "__main__":
    unittest.main()
