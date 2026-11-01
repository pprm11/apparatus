"""Person install (tools/onboard.py): a second person gets the shared layers and their own id, and nothing of the
owner's personal or company layers.

Everything runs in a temporary HOME against bare git repos on disk (`--git-host local:DIR`), so no GitHub account
is needed. Per-person privacy terms use a synthetic local file inside the temporary context home.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import layers  # noqa: E402
import onboard  # noqa: E402
import privacy  # noqa: E402
import scheduler  # noqa: E402

CANARY_ID = "CANARY-PERSONAL-ID-7731"
CANARY_COMPANY = "CANARY-OTHER-COMPANY-5520"
CANARY_EGO = "CANARY-OWNER-EGO-4417"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_NOSYSTEM": "1"}
LOCAL_TERMS = {
    "patterns": [{"name": "owner-name", "regex": "restricted-owner"},
                 {"name": "colleague-name", "regex": "restricted-colleague"}],
    "forbidden_layer_repos": ["(^|/)ego-other(\\.git)?$", "(^|/)retired-layer(\\.git)?$"],
    "personal_levels": ["id"],
}


def git(*argv, cwd=None):
    res = subprocess.run(["git", *argv], cwd=cwd, env=dict(os.environ, **GIT_ENV), capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return res.stdout.strip()


def make_shared(remote: Path, owner: str, repo: str, layer: dict, files: dict[str, str]) -> str:
    """A bare repo `remote/owner/repo.git` holding a layer; returns its path as the URL."""
    work = remote / "_work" / owner / repo
    work.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=work)
    (work / "layer.json").write_text(json.dumps(layer), encoding="utf-8")
    for rel, text in files.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(text, encoding="utf-8")
    git("add", "-A", cwd=work)
    git("commit", "-q", "-m", "feat: layer", cwd=work)
    bare = remote / owner / f"{repo}.git"
    bare.parent.mkdir(parents=True, exist_ok=True)
    git("clone", "-q", "--bare", str(work), str(bare))
    return str(bare)


class Fixture(unittest.TestCase):
    """A temp HOME, a remote folder with the shared layers and two decoys that must never be installed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.home = self.base / "home"
        self.home.mkdir()
        local = self.home / ".claude" / "privacy-terms.local.json"
        local.parent.mkdir()
        local.write_text(json.dumps(LOCAL_TERMS), encoding="utf-8")
        self.remote = self.base / "remote"
        env = dict(os.environ, **GIT_ENV, HOME=str(self.home), USERPROFILE=str(self.home),
                   SUPEREGO_HOME=str(self.base / "state"))
        for k in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "COMPANIES_FILE"):
            env.pop(k, None)
        self.env = env
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.lines: list[str] = []
        self.ctx = onboard.Ctx(sh=onboard.Sh(env), home=self.home, say=self.lines.append, interactive=False)
        team = "teamx"
        self.coll = make_shared(self.remote, "owner", f"collective-{team}", {
            "level": "collective", "name": team, "mode": "readonly", "globals": ["team-glossary.md"], "rules": [],
            "dirs": [], "files": [], "company": team}, {"global/team-glossary.md": "# Glossary\n\n- **term-a**: shared.\n"})
        self.ego = make_shared(self.remote, "owner", f"ego-{team}", {
            "level": "ego", "name": team, "globals": ["glossario-teamx.md"], "rules": [], "dirs": [], "files": [],
            "company": team}, {"global/glossario-teamx.md": f"# Glossario TeamX\n\n- **owner-only**: {CANARY_EGO}\n"})
        # decoys: the owner's personal layer and another company's ego, with canaries inside
        other = "ego-other"
        self.decoy_ego = make_shared(self.remote, "owner", other, {
            "level": "ego", "name": "other", "globals": ["g.md"], "rules": [], "dirs": [], "files": []},
            {"global/g.md": f"{CANARY_COMPANY}\n"})
        self.decoy_id = make_shared(self.remote, "owner", "id-context", {
            "level": "id", "globals": ["g.md"], "rules": [], "dirs": [], "files": []}, {"global/g.md": f"{CANARY_ID}\n"})

    def argv(self, *extra, jobs="plan"):
        return ["init", "--name", "Test Person", "--github", "testperson", "--yes", "--git-host", f"local:{self.remote}",
                "--jobs", jobs, "--layer", f"collective:teamx={self.coll}",
                "--root", "teamx=~/Work/teamx", *extra]

    def run_cli(self, argv):
        return onboard.main(["--claude-home", str(self.home / ".claude")] + argv, ctx=self.ctx)

    def all_text(self) -> str:
        out = []
        for p in self.home.rglob("*"):
            if p.is_file() and ".git" not in p.parts:
                try:
                    out.append(p.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError):
                    pass
        return "\n".join(out)


class InstallTest(Fixture):
    def test_init_installs_composes_and_doctor_is_green(self):
        rc = self.run_cli(self.argv())
        self.assertEqual(rc, 0, "\n".join(self.lines))
        claude = (self.home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        agents = (self.home / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
        for text in (claude, agents.replace("\r\n", "\n")):
            self.assertIn("team-glossary.md" if text is claude else "term-a", text)
        self.assertIn("teamx", agents, "the person's own ego, made from the template, is composed")
        manifest = json.loads((self.home / "Codes" / "psique" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([l["level"] for l in manifest["layers"]], ["superego", "collective", "ego", "id"])
        self.assertEqual([l.get("mode") for l in manifest["layers"]], ["readonly", "readonly", None, None],
                         "superego and the collective are shared and read-only; ego and id are the person's own")
        ego = next(l for l in manifest["layers"] if l["level"] == "ego")
        self.assertIn("testperson", ego["repo"])
        self.assertTrue((self.remote / "testperson" / "ego-teamx.git").is_dir(), "own private ego repo")
        self.assertEqual(manifest["default_level"], "id")
        for repo in ("psique", "id-context"):  # created in HIS account
            self.assertTrue((self.remote / "testperson" / f"{repo}.git").is_dir(), repo)
        self.assertFalse(any("[failed]" in l or "FAIL]" in l for l in self.lines), self.lines)

    def test_nothing_from_the_owner_personal_or_other_company_layers(self):
        self.assertEqual(self.run_cli(self.argv()), 0)
        text = self.all_text()
        self.assertNotIn(CANARY_ID, text)
        self.assertNotIn(CANARY_COMPANY, text)
        self.assertNotIn(CANARY_EGO, text, "the owner's ego never reaches the other person")
        self.assertFalse((self.remote / "owner" / "ego-teamx.git").exists() and (self.home / "Codes" / "owner").exists())
        self.assertFalse((self.home / "Codes" / "ego-other").exists())
        restored = [p for p in (self.home / ".claude").rglob("*")
                    if p.is_file() and p.name != "privacy-terms.local.json"]
        hits = privacy.scan_paths([*restored, self.home / ".codex" / "AGENTS.md"],
                                  privacy.patterns(allow_words=["testperson", "Test", "Person"]), self.home)
        self.assertEqual([h for h in hits if not (h.path.endswith("AGENTS.md") and h.line == 1)], [])

    def test_decoy_layers_are_refused(self):
        argv = self.argv("--layer", f"ego:other={self.decoy_ego}")
        self.assertEqual(self.run_cli(argv), 1)
        self.assertFalse((self.home / ".claude" / "CLAUDE.md").exists())
        argv = self.argv("--layer", f"ego:teamx={self.ego}")
        self.assertEqual(self.run_cli(argv), 1, "someone else's ego is never attachable, even the owner's own")
        self.assertNotIn(CANARY_EGO, self.all_text())
        argv = self.argv("--layer", f"ego:me={self.decoy_id}")
        self.assertEqual(self.run_cli(argv), 1, "an id of someone else is not attachable")
        self.assertNotIn(CANARY_ID, self.all_text())

    def test_a_term_in_a_shared_layer_stops_the_install(self):
        leaky = make_shared(self.remote, "owner", "collective-leaky", {
            "level": "collective", "name": "leaky", "mode": "readonly", "globals": ["g.md"], "rules": [], "dirs": [],
            "files": [], "company": "leaky"}, {"global/g.md": "Maintained by restricted-owner for the team.\n"})
        argv = self.argv()
        argv[argv.index(f"collective:teamx={self.coll}")] = f"collective:leaky={leaky}"
        self.assertEqual(self.run_cli(argv), 1)
        self.assertTrue(any("LEAKED" in l for l in self.lines), self.lines)
        self.assertFalse((self.home / ".claude" / "CLAUDE.md").exists())
        self.assertFalse((self.home / ".claude" / "g.md").exists(), "nothing is restored when the gate trips")

    def test_a_term_in_a_shared_layer_uses_the_selected_context_home(self):
        selected = self.home / "selected-context"
        selected.mkdir()
        # The process environment still points at the default context; the install has its own selection.
        local = self.home / ".claude" / "privacy-terms.local.json"
        local.replace(selected / local.name)
        self.ctx.sh.env["CLAUDE_CONFIG_DIR"] = str(selected)
        leaky = make_shared(self.remote, "owner", "collective-selected", {
            "level": "collective", "name": "selected", "mode": "readonly", "globals": ["g.md"], "rules": [],
            "dirs": [], "files": [], "company": "selected"}, {"global/g.md": "restricted-owner\n"})
        argv = self.argv()
        argv[argv.index(f"collective:teamx={self.coll}")] = f"collective:selected={leaky}"
        self.assertEqual(self.run_cli(argv), 1)
        self.assertTrue(any("LEAKED" in line for line in self.lines), self.lines)
        self.assertFalse((selected / "g.md").exists())

    def test_rerun_changes_nothing(self):
        self.assertEqual(self.run_cli(self.argv()), 0)
        first = (self.home / ".claude" / "CLAUDE.md").read_bytes()
        commits = git("rev-list", "--count", "HEAD", cwd=self.home / "Codes" / "id-context")
        self.assertEqual(self.run_cli(self.argv()), 0, "\n".join(self.lines))
        self.assertEqual((self.home / ".claude" / "CLAUDE.md").read_bytes(), first)
        self.assertEqual(git("rev-list", "--count", "HEAD", cwd=self.home / "Codes" / "id-context"), commits)

    def test_default_level_is_id_so_unlabeled_notes_stay_private(self):
        self.assertEqual(self.run_cli(self.argv()), 0)
        mem = self.home / ".claude" / "projects" / "k" / "memory"
        mem.mkdir(parents=True)
        (mem / "mine.md").write_text("---\nname: mine\n---\nplain note\n", encoding="utf-8")
        (mem / "team.md").write_text("---\nname: team\nlevel: ego\n---\nfor the team\n", encoding="utf-8")
        self.assertEqual(self.run_cli(["update", "--push", "--no-pull"]), 0, "\n".join(self.lines))
        pushed = git("ls-tree", "-r", "--name-only", "HEAD", cwd=self.remote / "testperson" / "id-context.git")
        self.assertIn("memory/k/mine.md", pushed)
        self.assertNotIn("team.md", pushed, "a note labeled for the ego never goes to the id repo")
        in_ego = git("ls-tree", "-r", "--name-only", "HEAD", cwd=self.remote / "testperson" / "ego-teamx.git")
        self.assertIn("memory/k/team.md", in_ego, "it goes to the person's own ego")

    def test_update_reaches_the_shared_layers(self):
        self.assertEqual(self.run_cli(self.argv()), 0)
        work = self.remote / "_work" / "owner" / "collective-teamx"
        (work / "global" / "team-glossary.md").write_text("# Glossary\n\n- **term-b**: new.\n", encoding="utf-8")
        git("commit", "-q", "-am", "feat: term b", cwd=work)
        git("push", "-q", self.coll, "HEAD:main", cwd=work)
        self.assertEqual(self.run_cli(["update"]), 0, "\n".join(self.lines))
        self.assertIn("term-b", (self.home / ".claude" / "team-glossary.md").read_text(encoding="utf-8"))
        self.assertIn("term-b", (self.home / ".codex" / "AGENTS.md").read_text(encoding="utf-8"))

    def test_uninstall_restores_the_own_files_and_keeps_the_repos(self):
        (self.home / ".claude").mkdir(exist_ok=True)
        (self.home / ".claude" / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
        self.assertEqual(self.run_cli(self.argv()), 0)
        self.assertEqual(self.run_cli(["uninstall"]), 0)
        self.assertEqual((self.home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8"), "my own rules\n")
        self.assertFalse((self.home / ".claude" / "team-glossary.md").exists())
        self.assertTrue((self.remote / "testperson" / "id-context.git").is_dir(), "the remote repo stays")

    def test_contribute_start_and_submit_use_a_worktree_and_open_a_pr(self):
        self.assertEqual(self.run_cli(self.argv()), 0)

        class FakeGh(onboard.Sh):
            calls: list = []

            def run(self, argv, **kw):
                if argv[0] == "gh":
                    FakeGh.calls.append(list(argv))
                    return subprocess.CompletedProcess(argv, 0, "", "")
                return super().run(argv, **kw)

        self.ctx.sh = FakeGh(self.env)
        self.assertEqual(self.run_cli(["contribute", "start", "collective", "new term"]), 0, "\n".join(self.lines))
        work = self.home / "Codes" / "contrib" / "collective-teamx-new-term"
        self.assertTrue(work.is_dir())
        (work / "proposed").mkdir()
        (work / "proposed" / "term.md").write_text("- **term-c**: proposed.\n", encoding="utf-8")
        self.assertEqual(self.run_cli(["contribute", "submit", str(work), "-m", "feat: add term c"]), 0,
                         "\n".join(self.lines))
        self.assertIn("contrib/testperson/new-term", git("branch", "--list", cwd=self.remote / "owner" / "collective-teamx.git"))
        self.assertTrue(any(c[:3] == ["gh", "pr", "create"] for c in FakeGh.calls), FakeGh.calls)
        self.assertEqual(self.run_cli(["contribute", "submit", str(work), "-m", "bad message"]), 1)
        self.assertEqual((self.home / "Codes" / "collective-teamx").exists(), True)
        self.assertEqual(git("status", "--porcelain", cwd=self.home / "Codes" / "collective-teamx"), "",
                         "the shared clone stays untouched")


class JobsTest(Fixture):
    def test_one_python_job_per_os_and_no_bash(self):
        self.assertEqual(self.run_cli(self.argv()), 0)
        manifest = self.home / "Codes" / "psique" / "manifest.json"
        for plat in ("win32", "darwin", "linux"):
            jobs = scheduler.jobs_for(manifest, plat)
            self.assertEqual([j.name for j in jobs], ["superego-testperson-update"], plat)
            self.assertEqual(jobs[0].short, "update")
            self.assertNotIn("bash", " ".join(jobs[0].argv).lower())
        self.assertTrue(any("superego-testperson-update" in l for l in self.lines))


class SuperegoPayloadTest(unittest.TestCase):
    """What superego puts on another person's machine carries no owner, company or client name."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        local = Path(tmp.name) / "privacy-terms.local.json"
        local.write_text(json.dumps(LOCAL_TERMS), encoding="utf-8")
        patcher = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_payload_templates_and_installer_are_clean(self):
        man = {"layers": [{"level": "superego", "path": str(ROOT)}]}
        layer = {"level": "superego", "path": str(ROOT / "superego"), "config": layers.read_json(str(ROOT / "superego" / "layer.json"))}
        del man
        pats = privacy.patterns()
        paths = onboard.layer_payload(layer) + [ROOT / "templates", ROOT / "install.sh", ROOT / "install.ps1",
                                                ROOT / "tools" / "onboard.py", ROOT / "tools" / "privacy.py"]
        docs = ROOT / "docs" / "instalar.pt-BR.md"
        if docs.exists():
            paths.append(docs)
        hits = privacy.scan_paths(paths, pats, ROOT)
        self.assertEqual([str(h) for h in hits if "skills/neon" not in h.path], [])

    def test_every_skill_is_clean_or_explicitly_excluded(self):
        cfg = layers.read_json(str(ROOT / "superego" / "layer.json"))
        excluded = set(cfg.get("install_exclude", {}).get("skills", []))
        pats = privacy.patterns()
        for sk in sorted((ROOT / "superego" / "skills").iterdir()):
            if not sk.is_dir() or sk.name in excluded or sk.name.startswith("neon"):
                continue
            self.assertEqual(privacy.scan_paths([sk], pats, ROOT), [], f"skill {sk.name}: clean it or add it to install_exclude")
        for name in excluded:
            self.assertTrue((ROOT / "superego" / "skills" / name).is_dir(), f"install_exclude names a missing skill: {name}")

    def test_forbidden_layer_names(self):
        cfg = privacy.load_config()
        for name in ("ego-other", "retired-layer"):
            self.assertTrue(privacy.forbidden_layer(f"https://example.com/o/{name}.git", cfg), name)
        self.assertIsNone(privacy.forbidden_layer("https://example.com/o/ego-teamx.git", cfg))

    def test_own_name_is_allowed_for_that_person_only(self):
        word = "restricted-colleague"
        text = f"{word} wrote this\n"
        self.assertTrue(privacy.scan_text(text, privacy.patterns(), "f"))
        self.assertEqual(privacy.scan_text(text, privacy.patterns(allow_words=[word]), "f"), [])


if __name__ == "__main__":
    unittest.main()
