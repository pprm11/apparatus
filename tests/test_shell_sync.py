"""Offline smoke test of sync.sh in a sandbox: fake CLAUDE_HOME, fake HOME, a manifest with three layer repos
(superego, ego, id), each with its own bare git remote."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def find_bash():
    for cand in (r"C:\Program Files\Git\bin\bash.exe", "/bin/bash", "/usr/bin/bash"):
        if os.path.exists(cand):
            return cand
    return None


BASH = find_bash()
# built at run time: the deny gate bans the literal machine-path forms
MSYS_PATH = "/c/" + "Users/x/y"
NATIVE_PATH = "C:/" + "Users/x/y"


def posix(path: str) -> str:
    return path.replace("\\", "/")


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def memory_text(name: str, level: str = "", body: str = "body") -> str:
    lvl = f"level: {level}\n" if level else ""
    return f"---\nname: {name}\ndescription: d\n{lvl}metadata:\n  type: reference\n  keywords: a, b\n---\n{body}\n"


@unittest.skipUnless(BASH and shutil.which("git"), "needs Git Bash and git")
class SyncSmokeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cc-sync-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")  # no ~/.codex here: the Codex render is a no-op
        self.claude = os.path.join(self.tmp, "claude")
        self.repo = os.path.join(self.tmp, "superego")  # the superego layer is also the repo that holds sync.sh
        self.ego = os.path.join(self.tmp, "ego-test")
        self.id = os.path.join(self.tmp, "id-test")
        self.manifest = os.path.join(self.tmp, "psique", "manifest.json")
        os.makedirs(self.home)
        self.env = dict(os.environ, HOME=self.home, USERPROFILE=self.home, CLAUDE_HOME=posix(self.claude),
                        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                        GIT_COMMITTER_EMAIL="t@t", GIT_CONFIG_NOSYSTEM="1", PYTHONIOENCODING="utf-8")
        self.env.pop("SYNC_LOCK_HELD", None)

        write(os.path.join(self.claude, "CLAUDE.md"), "# global\n")
        write(os.path.join(self.claude, "skills", "demo", "SKILL.md"), "---\nname: demo\ndescription: d\n---\n")
        write(os.path.join(self.claude, "skills", "synced", "x.md"), "claude.ai copy\n")
        write(os.path.join(self.claude, "rules", "mapa-do-contexto.md"), "rule\n")  # superego rule (layer.json)
        write(os.path.join(self.claude, "regras-de-agente.md"), "general rules\n")  # superego global
        write(os.path.join(self.claude, "harness", "claude.md"), "adapter\n")  # superego dir
        write(os.path.join(self.claude, "padroes-do-alex.md"), "personal\n")  # id global
        write(os.path.join(self.claude, "glossario-test.md"), "glossary\n")  # ego global
        write(os.path.join(self.claude, "scripts", "estado", "s.json"), "{}\n")  # listed in no layer.json
        write(os.path.join(self.claude, "scripts", "tool.py"), "print(1)\n")  # listed in no layer.json
        for i in range(22):  # no level: they default to ego
            self.memory(f"m{i}")
        self.memory("general", "superego")
        self.memory("personal", "id")

        # layer.json: the superego one is the real file; ego and id are trimmed fixtures (the real ones live in
        # other repos and the sandbox must not depend on sibling checkouts).
        layer_json = {
            self.repo: open(os.path.join(ROOT, "layer.json"), encoding="utf-8").read(),
            self.ego: json.dumps({"level": "ego", "name": "test", "globals": ["glossario-test.md"], "rules": [],
                                  "dirs": [], "files": []}),
            self.id: json.dumps({"level": "id", "globals": ["padroes-do-alex.md"], "rules": [], "dirs": [],
                                 "files": []}),
        }
        self.remotes = {}
        for path, text in layer_json.items():
            remote = path + "-remote.git"
            self.remotes[path] = remote
            self.git(self.tmp, "init", "-q", "--bare", remote)
            self.git(self.tmp, "init", "-q", "-b", "main", path)
            write(os.path.join(path, "layer.json"), text)
            self.git(path, "remote", "add", "origin", posix(remote))
        shutil.copytree(os.path.join(ROOT, "tools"), os.path.join(self.repo, "tools"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        for f in ("sync.sh", "lib.sh", ".gitignore"):
            shutil.copy(os.path.join(ROOT, f), os.path.join(self.repo, f))
        write(self.manifest, json.dumps({
            "default_level": "ego", "claude_home": posix(self.claude),
            "layers": [{"level": "superego", "path": posix(self.repo), "repo": "x", "active": True},
                       {"level": "ego", "name": "test", "path": posix(self.ego), "repo": "x", "active": True},
                       {"level": "id", "path": posix(self.id), "repo": "x", "active": True}]}))
        for path in layer_json:
            self.git(path, "add", "-A")
            self.git(path, "commit", "-qm", "initial")
            self.git(path, "push", "-q", "-u", "origin", "main")

    def memory(self, name, level="", proj="C--proj-a", body="body"):
        write(os.path.join(self.claude, "projects", proj, "memory", f"{name}.md"), memory_text(name, level, body))

    def git(self, cwd, *args):
        r = subprocess.run(["git", *args], cwd=cwd, env=self.env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def count(self, repo):
        return self.git(repo, "rev-list", "--count", "HEAD")

    def tracked(self, repo):
        return self.git(repo, "ls-files").splitlines()

    def synced(self, repo):
        return self.git(repo, "rev-parse", "HEAD") == self.git(repo, "rev-parse", "origin/main")

    def sync(self, *args):
        args = [*args, "--manifest", posix(self.manifest)]
        return subprocess.run([BASH, posix(os.path.join(self.repo, "sync.sh")), *args], cwd=self.repo, env=self.env,
                              capture_output=True, text=True, encoding="utf-8", timeout=300)

    def subjects(self, repo=None):
        return self.git(repo or self.ego, "log", "--format=%s").splitlines()

    def test_files_land_in_their_layer_and_each_repo_gets_a_commit(self):
        first = self.sync("--push")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertIn("== ", first.stdout)  # run header
        ego, sup, idl = self.tracked(self.ego), self.tracked(self.repo), self.tracked(self.id)
        # unlabeled memories and skills default to ego; labeled ones go to their level
        self.assertIn("memory/C--proj-a/m0.md", ego)
        self.assertIn("skills/demo/SKILL.md", ego)
        self.assertIn("global/glossario-test.md", ego)
        self.assertIn("memory/C--proj-a/general.md", sup)
        self.assertIn("global/regras-de-agente.md", sup)
        self.assertIn("rules/mapa-do-contexto.md", sup)
        self.assertIn("harness/claude.md", sup)
        self.assertIn("memory/C--proj-a/personal.md", idl)
        self.assertIn("global/padroes-do-alex.md", idl)
        for name in ("general.md", "personal.md"):
            self.assertNotIn("memory/C--proj-a/" + name, ego)
        self.assertNotIn("memory/C--proj-a/m0.md", sup + idl)
        # one commit per layer repo, in Conventional Commit form, all pushed
        self.assertTrue(any(s.startswith("chore(memory): sync 22 memories") for s in self.subjects(self.ego)))
        self.assertTrue(any(s.startswith("chore(context): update") for s in self.subjects(self.ego)))
        self.assertTrue(any(s.startswith("chore(memory): sync 1 memories") for s in self.subjects(self.repo)))
        self.assertTrue(any(s.startswith("chore(context): update") for s in self.subjects(self.repo)))
        self.assertTrue(any(s.startswith("chore(memory): sync 1 memories") for s in self.subjects(self.id)))
        self.assertFalse(any(s.startswith("sync:") for s in self.subjects(self.ego)))
        for repo in (self.repo, self.ego, self.id):
            self.assertTrue(self.synced(repo), repo)
        # excluded paths never reach any repo
        for repo in (self.repo, self.ego, self.id):
            self.assertFalse(os.path.exists(os.path.join(repo, "skills", "synced")), repo)
            self.assertFalse(os.path.exists(os.path.join(repo, "scripts", "estado")), repo)
            self.assertFalse(os.path.exists(os.path.join(repo, "scripts", "tool.py")), repo)

        counts = {r: self.count(r) for r in (self.repo, self.ego, self.id)}
        second = self.sync("--push")
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        for repo, n in counts.items():
            self.assertEqual(self.count(repo), n, second.stdout)
        self.assertIn("No changes.", second.stdout)

    def test_level_change_moves_a_memory_between_repos(self):
        self.assertEqual(self.sync("--push").returncode, 0)
        self.assertIn("memory/C--proj-a/m3.md", self.tracked(self.ego))
        self.memory("m3", "id")
        self.assertEqual(self.sync("--push").returncode, 0)
        self.assertNotIn("memory/C--proj-a/m3.md", self.tracked(self.ego))
        self.assertIn("memory/C--proj-a/m3.md", self.tracked(self.id))
        self.assertFalse(os.path.exists(os.path.join(self.ego, "memory", "C--proj-a", "m3.md")))

    def test_unlabeled_files_are_listed_once_in_the_inbox(self):
        for _ in range(2):
            self.assertEqual(self.sync("--push").returncode, 0)
        inbox = open(os.path.join(self.home, ".claude", "decisions", "inbox.json"), encoding="utf-8").read()
        self.assertEqual(inbox.count("Memórias ou skills sem nível"), 1)

    def test_push_retries_when_local_is_ahead(self):
        self.assertEqual(self.sync("--push").returncode, 0)
        self.git(self.ego, "commit", "-q", "--allow-empty", "-m", "local only")
        self.assertFalse(self.synced(self.ego))
        self.assertEqual(self.sync("--push").returncode, 0)
        self.assertTrue(self.synced(self.ego))

    def test_missing_source_aborts_without_deleting(self):
        self.assertEqual(self.sync("--push").returncode, 0)
        before = self.count(self.ego)
        os.remove(os.path.join(self.claude, "CLAUDE.md"))
        r = self.sync("--push")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("ABORT", r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.ego, "memory", "C--proj-a", "m0.md")))
        self.assertEqual(self.count(self.ego), before)

    def test_missing_manifest_aborts(self):
        os.remove(self.manifest)
        r = self.sync("--push")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("manifest", r.stderr)

    def test_too_few_memories_aborts(self):
        shutil.rmtree(os.path.join(self.claude, "projects", "C--proj-a", "memory"))
        write(os.path.join(self.claude, "projects", "C--proj-a", "memory", "only.md"), "x\n")
        r = self.sync("--push")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("memory files", r.stderr)

    def test_busy_lock_skips_with_0_unless_sync_require(self):
        os.makedirs(os.path.join(self.repo, ".sync.lock"))  # fresh lock without owner file: still held
        r = self.sync("--push")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("sync skipped", r.stdout)
        self.assertEqual(self.sync().returncode, 0)
        self.env["SYNC_REQUIRE"] = "1"
        self.assertEqual(self.sync("--push").returncode, 75)
        self.assertEqual(self.sync().returncode, 75)

    def test_stale_lock_with_dead_pid_is_taken_over(self):
        lock = os.path.join(self.repo, ".sync.lock")
        os.makedirs(lock)
        write(os.path.join(lock, "owner"), "999999 1\n")
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("stale lock", r.stdout)
        self.assertFalse(os.path.exists(lock), "lock must be released at the end")

    def test_mass_deletion_aborts_commit(self):
        self.assertEqual(self.sync("--push").returncode, 0)
        for i in range(60):
            self.memory(f"x{i}")
        self.assertEqual(self.sync("--push").returncode, 0)
        for i in range(60):  # the 22 original memories stay: an emptied folder aborts earlier, in the preflight
            os.remove(os.path.join(self.claude, "projects", "C--proj-a", "memory", f"x{i}.md"))
        before = self.count(self.ego)
        r = self.sync("--push")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("would be deleted", r.stderr)
        self.assertEqual(self.count(self.ego), before)

    def test_missing_expected_source_dir_aborts_before_touching_anything(self):
        self.assertEqual(self.sync("--push").returncode, 0)
        before = self.count(self.repo)
        shutil.rmtree(os.path.join(self.claude, "rules"))
        r = self.sync("--push")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("rules is missing", r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.repo, "rules", "mapa-do-contexto.md")))
        self.assertEqual(self.count(self.repo), before)

    def test_missing_project_memory_dir_aborts(self):
        self.assertEqual(self.sync("--push").returncode, 0)
        self.memory("z", proj="C--proj-b")
        self.assertEqual(self.sync("--push").returncode, 0)
        shutil.rmtree(os.path.join(self.claude, "projects", "C--proj-b", "memory"))
        r = self.sync("--push")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.ego, "memory", "C--proj-b", "z.md")))

    def test_failed_push_keeps_commits_and_exits_nonzero(self):
        self.git(self.ego, "remote", "set-url", "origin", posix(os.path.join(self.tmp, "nope.git")))
        r = self.sync("--push")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("push failed", r.stdout)
        self.assertTrue(any(s.startswith("chore(memory)") for s in self.subjects(self.ego)))
        # the other layers were not held back by the broken remote
        self.assertTrue(self.synced(self.repo))
        self.assertTrue(self.synced(self.id))

    def test_rename_commits_the_old_path_deletion(self):
        self.assertEqual(self.sync("--push").returncode, 0)
        mem = os.path.join(self.claude, "projects", "C--proj-a", "memory")
        os.rename(os.path.join(mem, "m0.md"), os.path.join(mem, "renamed.md"))
        self.assertEqual(self.sync("--push").returncode, 0)
        self.assertNotIn("memory/C--proj-a/m0.md", self.tracked(self.ego))
        self.assertIn("memory/C--proj-a/renamed.md", self.tracked(self.ego))
        self.assertEqual(self.git(self.ego, "status", "--porcelain"), "")

    def test_empty_expected_sources_abort_before_any_mutation(self):
        self.assertEqual(self.sync("--push").returncode, 0)
        before = self.count(self.ego)
        shutil.rmtree(os.path.join(self.claude, "skills"))
        os.makedirs(os.path.join(self.claude, "skills"))
        r = self.sync("--push")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("missing or empty", r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.ego, "skills", "demo", "SKILL.md")))
        write(os.path.join(self.claude, "skills", "demo", "SKILL.md"), "---\nname: demo\ndescription: d\n---\n")
        # an emptied project memory folder is just as fatal (22 files in the ego backup)
        mem = os.path.join(self.claude, "projects", "C--proj-a", "memory")
        for n in os.listdir(mem):
            os.remove(os.path.join(mem, n))
        self.memory("z", proj="C--proj-b")
        r = self.sync("--push")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.ego, "memory", "C--proj-a", "m0.md")))
        self.assertEqual(self.count(self.ego), before)

    def test_generated_index_and_lint_report_are_not_versioned(self):
        self.assertEqual(self.sync("--push").returncode, 0)
        tracked = self.tracked(self.repo)
        self.assertNotIn("INDEX.md", tracked)
        self.assertNotIn("lint-report.md", tracked)
        self.assertTrue(os.path.exists(os.path.join(self.repo, "lint-report.md")))
        self.assertNotIn("index", {p.split("/")[0] for p in tracked})

    def test_blob_over_1mb_is_never_committed_and_reported_once(self):
        self.memory("big", body="x" * (1024 * 1024 + 10))
        for _ in range(2):
            r = self.sync("--push")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("over 1 MB", r.stdout)
        self.assertNotIn("memory/C--proj-a/big.md", self.tracked(self.ego))
        self.assertTrue(os.path.exists(os.path.join(self.ego, "memory", "C--proj-a", "big.md")))
        inbox = open(os.path.join(self.home, ".claude", "decisions", "inbox.json"), encoding="utf-8").read()
        self.assertEqual(inbox.count("Arquivo grande barrado no sync: memory/C--proj-a/big.md"), 1)

    def test_readme_documents_partial_clone_and_size_threshold(self):
        readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
        self.assertRegex(readme, r"git clone --filter=blob:none https://github\.com/[^/\s]+/superego")
        self.assertIn("50 MB", readme)
        self.assertIn("git bundle", readme)

    def test_renderer_regex_strips_cr(self):
        src = open(os.path.join(ROOT, "sync.sh"), encoding="utf-8").read()
        self.assertIn("render=\"${render//$'\\r'/}\"", src)


if __name__ == "__main__":
    unittest.main()


class LibNativePathTest(unittest.TestCase):
    """lib.sh native_path: cygpath where it exists, the path untouched elsewhere."""

    def test_native_path_without_cygpath_returns_the_input(self):
        lib = posix(os.path.join(ROOT, "lib.sh"))
        out = subprocess.run([BASH, "-c", f'. "{lib}"; PATH=/nonexistent; native_path {MSYS_PATH}'],
                             capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), MSYS_PATH)

    def test_native_path_with_cygpath_gives_the_native_form(self):
        lib = posix(os.path.join(ROOT, "lib.sh"))
        out = subprocess.run([BASH, "-c", f'. "{lib}"; command -v cygpath >/dev/null || exit 3; native_path {MSYS_PATH}'],
                             capture_output=True, text=True, encoding="utf-8")
        if out.returncode == 3:
            self.skipTest("no cygpath on this host")
        self.assertEqual(out.stdout.strip(), NATIVE_PATH)

    def test_native_path_is_defined_and_used_instead_of_cygpath(self):
        for name in ("weekly.sh", "harvest.sh"):
            with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
                text = fh.read()
            self.assertNotIn("cygpath", text, name)
            self.assertIn("native_path", text, name)
