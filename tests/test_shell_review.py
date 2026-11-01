"""Tests for the independent-review fixes: mirror safety, atomic copy, locks, validator, shared memory lock."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import mirror  # noqa: E402
import validate_harvest as vh  # noqa: E402
from test_shell_sync import BASH, posix  # noqa: E402
from test_shell_sync import write as _write  # noqa: E402


def write(path, text="x\n"):
    _write(path, text)


def run_mirror(*args):
    return subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "mirror.py"), *args],
                          capture_output=True, text=True, encoding="utf-8")


class MirrorSafetyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cc-mirror-safety-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src, self.dst = os.path.join(self.tmp, "s"), os.path.join(self.tmp, "d")

    def test_missing_source_never_removes_destination_without_flag(self):
        write(os.path.join(self.dst, "keep.md"))
        r = run_mirror(self.src, self.dst)
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(self.dst, "keep.md")))
        r = run_mirror(self.src, self.dst, "--allow-remove-dir")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.dst))

    def test_failed_copy_exits_nonzero_and_leaves_no_partial_file(self):
        write(os.path.join(self.src, "a.md"), "new content\n")
        write(os.path.join(self.dst, "a.md"), "old\n")
        real_copy2, real_sleep = shutil.copy2, mirror.time.sleep

        def half_copy(s, d, **kw):
            with open(d, "w") as fh:
                fh.write("trunc")
            raise PermissionError("held")

        shutil.copy2, mirror.time.sleep = half_copy, lambda s: None
        warnings = []
        try:
            mirror.mirror(self.src, self.dst, set(), set(), True, warnings)
        finally:
            shutil.copy2, mirror.time.sleep = real_copy2, real_sleep
        self.assertEqual(len(warnings), 1)
        with open(os.path.join(self.dst, "a.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "old\n")
        self.assertEqual(os.listdir(self.dst), ["a.md"])

    def test_exit_code_is_one_when_a_file_cannot_be_handled(self):
        write(os.path.join(self.src, "a.md"))
        os.makedirs(self.dst)
        code = (
            "import sys, shutil; sys.path.insert(0, r'%s'); import mirror; mirror.time.sleep = lambda s: None;"
            "shutil.copy2 = lambda *a, **k: (_ for _ in ()).throw(PermissionError('x'));"
            "sys.argv = ['m', r'%s', r'%s']; sys.exit(mirror.main())" % (os.path.join(ROOT, "tools"), self.src, self.dst))
        r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stderr)

    def test_same_size_and_close_mtime_but_different_bytes_is_copied(self):
        write(os.path.join(self.src, "a.md"), "aaaa\n")
        write(os.path.join(self.dst, "a.md"), "bbbb\n")
        st = os.stat(os.path.join(self.src, "a.md"))
        os.utime(os.path.join(self.dst, "a.md"), ns=(st.st_atime_ns, st.st_mtime_ns + 500_000_000))
        self.assertEqual(run_mirror(self.src, self.dst).returncode, 0)
        with open(os.path.join(self.dst, "a.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "aaaa\n")

    def test_no_delete_skips_type_conflicts(self):
        write(os.path.join(self.src, "x"), "file\n")
        write(os.path.join(self.dst, "x", "inner.md"))
        r = run_mirror(self.src, self.dst, "--no-delete")
        self.assertEqual(r.returncode, 0)
        self.assertIn("conflict", r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.dst, "x", "inner.md")))


class ValidatorOutputTest(unittest.TestCase):
    GOOD = "---\nname: {n}\ndescription: d\nmetadata:\n  type: project\n---\nbody\n"

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cc-vh2-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.out = os.path.join(self.tmp, "out")
        self.projects = os.path.join(self.tmp, "projects")
        os.makedirs(os.path.join(self.projects, "P", "memory"))

    def test_output_is_lf_only(self):
        write(os.path.join(self.out, "P", "a.md"), self.GOOD.format(n="a"))
        r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "validate_harvest.py"), self.out,
                            self.projects], capture_output=True)
        self.assertEqual(r.returncode, 0)
        self.assertNotIn(b"\r", r.stdout)
        self.assertEqual(r.stdout, b"OK\tP/a.md\n")

    def test_case_variants_of_reserved_and_existing_names_are_rejected(self):
        write(os.path.join(self.projects, "P", "memory", "MEMORY.md"), "index\n")
        write(os.path.join(self.projects, "P", "memory", "Foo.md"), self.GOOD.format(n="Foo").replace("project", "reference"))
        write(os.path.join(self.out, "P", "memory.md"), self.GOOD.format(n="memory"))
        write(os.path.join(self.out, "P", "foo.md"), self.GOOD.format(n="foo"))
        res = vh.validate(self.out, self.projects)
        self.assertEqual(sorted(line.split("\t")[0] for line in res), ["REJECT", "REJECT"])


@unittest.skipUnless(BASH, "needs Git Bash")
class LockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cc-lock-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.lock = posix(os.path.join(self.tmp, "x.lock"))
        self.lib = posix(os.path.join(ROOT, "lib.sh"))

    def bash(self, script, **kw):
        return subprocess.run([BASH, "-c", script], capture_output=True, text=True, encoding="utf-8", **kw)

    def test_only_one_contender_reclaims_a_stale_lock(self):
        os.makedirs(self.lock.replace("/", os.sep))
        write(os.path.join(self.tmp, "x.lock", "owner"), "999999 1 deadtoken\n")
        won = posix(os.path.join(self.tmp, "won.txt"))
        script = f'. "{self.lib}"; if lock_acquire "{self.lock}"; then echo $$ >> "{won}"; sleep 3; fi'
        procs = [subprocess.Popen([BASH, "-c", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                 for _ in range(6)]
        for p in procs:
            p.wait(timeout=60)
        with open(os.path.join(self.tmp, "won.txt"), encoding="utf-8") as fh:
            self.assertEqual(len(fh.read().split()), 1)

    def test_release_only_with_our_token(self):
        r = self.bash(f'. "{self.lib}"; lock_acquire "{self.lock}"; '
                      f'echo "$$ $(date +%s) someone-else" > "{self.lock}/owner"; lock_release "{self.lock}"; '
                      f'[ -d "{self.lock}" ] && echo kept')
        self.assertIn("kept", r.stdout, r.stderr)
        r = self.bash(f'. "{self.lib}"; rm -rf "{self.lock}"; lock_acquire "{self.lock}"; lock_release "{self.lock}"; '
                      f'[ -d "{self.lock}" ] && echo kept || echo gone')
        self.assertIn("gone", r.stdout, r.stderr)


@unittest.skipUnless(BASH, "needs Git Bash")
class MemoryLockTest(unittest.TestCase):
    """weekly.sh and harvest.sh share .memory.lock."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cc-memlock-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for f in ("lib.sh", "weekly.sh", "harvest.sh"):
            shutil.copy(os.path.join(ROOT, f), self.tmp)
        os.makedirs(os.path.join(self.tmp, ".memory.lock"))  # fresh, no owner: held
        self.ego = os.path.join(self.tmp, "ego")
        os.makedirs(self.ego)
        self.manifest = os.path.join(self.tmp, "manifest.json")
        write(self.manifest, json.dumps({"default_level": "ego", "layers": [
            {"level": "superego", "path": posix(self.tmp), "active": True},
            {"level": "ego", "path": posix(self.ego), "active": True}]}))

    def run_script(self, name, *args, **env):
        return subprocess.run([BASH, posix(os.path.join(self.tmp, name)), "--manifest", posix(self.manifest), *args],
                              cwd=self.tmp, capture_output=True, text=True,
                              encoding="utf-8", env=dict(os.environ, **env), timeout=120)

    def test_harvest_skips_while_memory_lock_is_held(self):
        r = self.run_script("harvest.sh")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("harvest skipped", r.stdout)

    def test_weekly_fails_while_memory_lock_is_held(self):
        r = self.run_script("weekly.sh", WEEKLY_LOCK_WAIT_S="0")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(".memory.lock", r.stderr)

    def test_weekly_and_harvest_need_an_ego_layer_in_the_manifest(self):
        write(self.manifest, json.dumps({"default_level": "ego", "layers": [
            {"level": "superego", "path": posix(self.tmp), "active": True}]}))
        for name in ("weekly.sh", "harvest.sh"):
            r = self.run_script(name, WEEKLY_LOCK_WAIT_S="0")
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("no active ego layer", r.stderr)

    def test_model_edits_only_the_ego_layer(self):
        for name in ("weekly.sh", "harvest.sh"):
            src = open(os.path.join(ROOT, name), encoding="utf-8").read()
            self.assertNotIn("claude-context", src)
            self.assertNotIn("Edit($OWN/memory", src)
            self.assertNotIn(">> log.md", src)
        weekly = open(os.path.join(ROOT, "weekly.sh"), encoding="utf-8").read()
        for p in ("memory/**", "log.md", "proposals.md", "reports/**"):
            self.assertIn(f"Edit($EGO_P/{p})", weekly)
        self.assertIn("Edit($OWN/.work/**)", weekly)
        prompt = open(os.path.join(ROOT, "prompts", "weekly-maintenance.md"), encoding="utf-8").read()
        self.assertNotIn("{{REPO}}/memory", prompt)
        self.assertIn("{{EGO}}/memory/", prompt)
        self.assertIn("{{REPO}}/lint-report.md", prompt)

    def test_harvest_reads_validator_through_a_manifest_file(self):
        src = open(os.path.join(ROOT, "harvest.sh"), encoding="utf-8").read()
        self.assertNotIn("< <(python -I tools/validate_harvest.py", src)
        self.assertIn("manifest", src)


class RoundTwoTest(unittest.TestCase):
    def test_vanished_source_during_copy_is_a_failure_but_vanished_delete_is_fine(self):
        tmp = tempfile.mkdtemp(prefix="cc-r2-")
        self.addCleanup(shutil.rmtree, tmp, True)
        warnings = []

        def gone():
            raise FileNotFoundError("gone")

        self.assertFalse(mirror.retry(gone, "copy", warnings))
        self.assertEqual(len(warnings), 1)
        self.assertTrue(mirror.retry(gone, "delete", warnings, True))
        self.assertEqual(len(warnings), 1)

    def test_harvest_routes_skill_draft_failures_through_apply_failed(self):
        src = open(os.path.join(ROOT, "harvest.sh"), encoding="utf-8").read()
        block = src[src.index("skill-drafts/*/"):src.index("echo \"- rejected by validation")]
        self.assertIn("apply_failed=", block)
        self.assertIn("continue", block)


@unittest.skipUnless(BASH and shutil.which("git"), "needs Git Bash and git")
class WeeklyCopyBackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cc-weekly-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        write(os.path.join(self.repo, "memory", "p", "a.md"), "baseline\n")
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
            subprocess.run(["git", *args], cwd=self.repo, env=env, check=True, capture_output=True)
        src = open(os.path.join(ROOT, "weekly.sh"), encoding="utf-8").read()
        funcs = src[src.index("unchanged_since_baseline() {"):src.index("valid_memory()")]
        self.script = funcs

    def bash(self, body):
        return subprocess.run([BASH, "-c", self.script + "\n" + body], cwd=self.repo, capture_output=True, text=True,
                              encoding="utf-8")

    def test_missing_destination_that_existed_at_baseline_is_a_conflict(self):
        dest = posix(os.path.join(self.tmp, "gone.md"))
        self.assertEqual(self.bash(f'unchanged_since_baseline memory/p/a.md "{dest}"').returncode, 1)
        # a brand-new file with no destination is fine to create
        self.assertEqual(self.bash(f'unchanged_since_baseline memory/p/new.md "{dest}"').returncode, 0)

    def test_safe_copy_failure_leaves_no_partial_file_and_success_replaces(self):
        src = posix(os.path.join(self.repo, "memory", "p", "a.md"))
        missing_dir = posix(os.path.join(self.tmp, "nodir", "x.md"))
        r = self.bash(f'safe_copy "{src}" "{missing_dir}"')
        self.assertEqual(r.returncode, 1)
        dest = os.path.join(self.tmp, "live.md")
        write(dest, "live\n")
        self.assertEqual(self.bash(f'safe_copy "{src}" "{posix(dest)}"').returncode, 0)
        with open(dest, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "baseline\n")
        self.assertEqual(sorted(os.listdir(self.tmp)), ["live.md", "repo"])


if __name__ == "__main__":
    unittest.main()
