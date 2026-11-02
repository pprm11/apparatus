"""Person install, second half: collective step, vault, jobs, uninstall and restore mode.

Same rules as test_onboard.py: temp HOME, bare repos, no GitHub, no real vault, no real scheduler (a fake backend
records what would be registered). The fake `bw`, `age-keygen` and `gh` live in FakeTools.
"""
import base64
import datetime
import json
import shutil
import subprocess
import sys
import unittest
from unittest import mock

from test_onboard import CANARY_COMPANY, CANARY_ID, ROOT, Fixture, git, make_shared  # noqa: F401

sys.path.insert(0, str(ROOT / "tools"))
import onboard  # noqa: E402
import scheduler  # noqa: E402

SECRET = "AGE-SECRET" + "-KEY-1FAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE"
RECIPIENT = "age1fakerecipientfakerecipientfakerecipientfakerecipientfak"


class FakeTools(onboard.Sh):
    """bw (an in-memory vault), age-keygen and gh answered in process; everything else runs for real."""
    notes: dict = {}
    calls: list = []

    def run(self, argv, **kw):
        a = [str(x) for x in argv]
        if a[0] == "bw":
            FakeTools.calls.append(a[:3])
            if a[1] == "status":
                return subprocess.CompletedProcess(argv, 0, json.dumps({"status": "unlocked"}), "")
            if a[1] == "get" and a[2] == "notes":
                note = FakeTools.notes.get(a[3])
                return subprocess.CompletedProcess(argv, 0 if note else 1, note or "", "" if note else "not found")
            if a[1:3] == ["create", "item"]:
                item = json.loads(base64.b64decode(kw["input"]))
                FakeTools.notes[item["name"]] = item["notes"]
            return subprocess.CompletedProcess(argv, 0, "", "")
        if a[0] == "age-keygen":
            if "-y" in a:
                return subprocess.CompletedProcess(argv, 0, RECIPIENT + "\n", "")
            return subprocess.CompletedProcess(argv, 0, f"# created: now\n# public key: {RECIPIENT}\n{SECRET}\n", "")
        if a[0] == "gh":
            FakeTools.calls.append(a[:4])
            return subprocess.CompletedProcess(argv, 0, "", "")
        return super().run(argv, **kw)


class FakeBackend:
    name = "fake"
    installed: set = set()

    def install(self, jobs):
        FakeBackend.installed |= {j.name for j in jobs}
        return [j.name for j in jobs]

    def remove(self, jobs):
        FakeBackend.installed -= {j.name for j in jobs}
        return [j.name for j in jobs]

    def status(self, jobs):
        return {j.name: j.name in FakeBackend.installed for j in jobs}


class V2(Fixture):
    def setUp(self):
        super().setUp()
        FakeTools.notes, FakeTools.calls, FakeBackend.installed = {}, [], set()
        self.env["BW_SESSION"] = "fake-session"
        self.ctx.sh = FakeTools(self.env)
        self.ctx.which = lambda c: f"/fake/{c}" if c in ("bw", "age", "age-keygen", "gh") else shutil.which(c)
        p = mock.patch.object(scheduler, "backend_for", return_value=FakeBackend())
        p.start()
        self.addCleanup(p.stop)

    def tree(self) -> dict:
        out = {}
        for p in sorted(self.home.rglob("*")):
            if ".git" in p.parts:
                continue
            out[p.relative_to(self.home).as_posix()] = p.read_bytes() if p.is_file() else None
        return out


class DoctorLayerCheckTest(V2):
    def test_superego_without_a_git_folder_is_fine_other_layers_need_their_clone(self):
        """Root cause of 8 failures seen on a worktree/copy of main: .git is a file there, or absent."""
        sup = self.base / "sup-copy"
        sup.mkdir()
        (sup / "layer.json").write_text(json.dumps({"level": "superego"}), encoding="utf-8")
        eg = self.base / "eg"
        eg.mkdir()
        (eg / "layer.json").write_text(json.dumps({"level": "ego"}), encoding="utf-8")
        man = self.base / "m.json"
        man.write_text(json.dumps({"layers": [{"level": "superego", "path": str(sup), "active": True},
                                              {"level": "ego", "path": str(eg), "active": True}]}), encoding="utf-8")
        got = {c.id: c.status for c in onboard.person_checks(self.ctx, man) if c.id.startswith("layer-")}
        self.assertEqual(got, {"layer-superego": "ok", "layer-ego": "fail"})


class CollectiveStepTest(V2):
    def test_new_collective_is_created_private_with_ci_and_deny_list(self):
        argv = ["init", "--name", "Test Person", "--github", "testperson", "--yes", "--git-host", f"local:{self.remote}",
                "--jobs", "skip", "--vault", "skip", "--new-collective", "newteam", "--deny-company", "acme",
                "--root", "newteam=~/Work/newteam"]
        self.assertEqual(self.run_cli(argv), 0, "\n".join(self.lines))
        clone = self.base / "clonecheck"
        git("clone", "-q", str(self.remote / "testperson" / "collective-newteam.git"), str(clone))
        for rel in ("ci/gates.py", ".github/workflows/ci.yml", "layer.json", "global/glossary.md", "CODEOWNERS", "registry.json"):
            self.assertTrue((clone / rel).is_file(), rel)
        self.assertEqual(json.loads((clone / "layer.json").read_text(encoding="utf-8"))["name"], "newteam")
        self.assertIn("@testperson", (clone / "CODEOWNERS").read_text(encoding="utf-8"))
        self.assertNotIn("{{", (clone / "CODEOWNERS").read_text(encoding="utf-8"))
        self.assertNotIn("<team>", (clone / "layer.json").read_text(encoding="utf-8"))
        manifest = json.loads((self.home / "Codes" / "self" / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("collective", [l["level"] for l in manifest["layers"]])

    def test_skip_the_collective(self):
        argv = ["init", "--name", "Test Person", "--github", "testperson", "--yes", "--git-host", f"local:{self.remote}",
                "--jobs", "skip", "--vault", "skip", "--no-collective"]
        self.assertEqual(self.run_cli(argv), 0, "\n".join(self.lines))
        manifest = json.loads((self.home / "Codes" / "self" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([l["level"] for l in manifest["layers"]], ["superego", "id"])

    def test_without_a_choice_it_asks_for_one_in_flags(self):
        argv = ["init", "--name", "T", "--github", "testperson", "--yes", "--git-host", f"local:{self.remote}", "--jobs", "skip",
                "--vault", "skip"]
        self.assertEqual(self.run_cli(argv), 1)

    def test_two_companies_never_mix(self):
        y_coll = make_shared(self.remote, "owner", "collective-teamy", {
            "level": "collective", "name": "teamy", "mode": "readonly", "globals": ["team-glossary.md"], "rules": [],
            "dirs": [], "files": [], "company": "teamy"}, {"global/team-glossary.md": "# Glossary\n\n- **only-y**: y.\n"})
        argv = self.argv("--layer", f"collective:teamy={y_coll}", jobs="skip") + ["--vault", "skip"]
        self.assertEqual(self.run_cli(argv), 0, "\n".join(self.lines))
        default = (self.home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertNotIn("team-glossary.md", default, "the default home loads no company layer when there are two")
        x_home, y_home = self.home / ".agent-homes" / "teamx", self.home / ".agent-homes" / "teamy"
        self.assertIn("term-a", (x_home / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertNotIn("only-y", (x_home / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertIn("only-y", (y_home / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertNotIn("term-a", (y_home / "AGENTS.md").read_text(encoding="utf-8"))


class VaultStepTest(V2):
    def argv_vault(self):
        return self.argv(jobs="apply") + ["--vault", "yes"]

    def test_identity_goes_to_own_vault_and_never_to_disk_or_output(self):
        self.assertEqual(self.run_cli(self.argv_vault()), 0, "\n".join(self.lines))
        self.assertEqual(FakeTools.notes["age-identity"].strip().splitlines()[-1], SECRET)
        recipient = (self.home / ".config" / "id-context" / "recipient").read_text(encoding="utf-8").strip()
        self.assertEqual(recipient, RECIPIENT)
        self.assertNotIn(SECRET, self.all_text() + "\n".join(self.lines), "the private key reaches neither disk nor output")
        raw = json.loads((self.home / "Codes" / "self" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["jobs"], ["update", "secrets"])
        self.assertIn("superego-testperson-secrets", FakeBackend.installed)
        self.assertTrue(any(c[:3] == ["bw", "create", "item"] for c in FakeTools.calls))

    def test_second_run_reuses_the_vault_key(self):
        self.assertEqual(self.run_cli(self.argv_vault()), 0)
        creates = sum(c[:3] == ["bw", "create", "item"] for c in FakeTools.calls)
        self.assertEqual(self.run_cli(self.argv_vault()), 0)
        self.assertEqual(sum(c[:3] == ["bw", "create", "item"] for c in FakeTools.calls), creates)
        self.assertTrue(any("reused" in l for l in self.lines))

    def test_locked_vault_is_skipped_not_fatal(self):
        self.env.pop("BW_SESSION")
        self.ctx.sh = FakeTools(dict(self.env))
        self.assertEqual(self.run_cli(self.argv_vault()), 0, "\n".join(self.lines))
        self.assertNotIn("age-identity", FakeTools.notes)
        self.assertTrue(any("locked" in l for l in self.lines))


class JobsTest2(V2):
    def test_next_run_is_pure(self):
        now = datetime.datetime(2026, 10, 31, 10, 25)
        self.assertEqual(scheduler.next_run(scheduler.Trigger("hourly", minute=20), now), datetime.datetime(2026, 10, 31, 11, 20))
        self.assertEqual(scheduler.next_run(scheduler.Trigger("hourly", minute=40), now), datetime.datetime(2026, 10, 31, 10, 40))
        monday = scheduler.next_run(scheduler.Trigger("weekly", weekday=0, hour=9), now)
        self.assertEqual((monday.weekday(), monday.hour), (0, 9))
        self.assertGreater(monday, now)

    def test_jobs_commands_and_initial_sync(self):
        self.assertEqual(self.run_cli(self.argv(jobs="apply") + ["--vault", "skip"]), 0, "\n".join(self.lines))
        self.assertEqual(FakeBackend.installed, {"superego-testperson-update"})
        self.assertTrue(any("initial sync" in l for l in self.lines), self.lines)
        self.lines.clear()
        self.assertEqual(self.run_cli(["jobs", "status"]), 0)
        self.assertTrue(any(l.startswith("update") and "registered" in l for l in self.lines), self.lines)
        self.assertTrue(any(l.startswith("secrets") and "disabled" in l for l in self.lines), self.lines)
        self.assertEqual(self.run_cli(["jobs", "enable", "secrets"]), 0, "\n".join(self.lines))
        self.assertIn("superego-testperson-secrets", FakeBackend.installed)
        self.assertEqual(self.run_cli(["jobs", "disable", "secrets"]), 0)
        self.assertNotIn("superego-testperson-secrets", FakeBackend.installed)
        self.assertEqual(self.run_cli(["jobs", "enable", "nope"]), 1)
        self.assertEqual(self.run_cli(["doctor"]), 0)
        self.assertTrue(any("job-update" in l and "registered" in l for l in self.lines), self.lines)


class UninstallTest(V2):
    def setUp(self):
        super().setUp()
        (self.home / ".claude").mkdir(exist_ok=True)  # the shared fixture already writes privacy-terms.local.json here
        (self.home / ".claude" / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
        (self.home / ".claude" / "settings.json").write_text('{"theme":"dark"}\n', encoding="utf-8")
        (self.home / "notes.txt").write_text("mine\n", encoding="utf-8")
        self.before = self.tree()

    def install(self, vault="skip"):
        self.assertEqual(self.run_cli(self.argv(jobs="apply") + ["--vault", vault]), 0, "\n".join(self.lines))

    def test_install_then_uninstall_leaves_the_home_as_before(self):
        self.install(vault="yes")
        self.assertNotEqual(self.tree(), self.before)
        self.lines.clear()
        self.assertEqual(self.run_cli(["uninstall"]), 0, "\n".join(self.lines))
        self.assertEqual(self.tree(), self.before)
        self.assertEqual(FakeBackend.installed, set())
        self.assertTrue((self.remote / "testperson" / "id.git").is_dir(), "remote repos are never deleted by default")
        self.assertIn("age-identity", FakeTools.notes, "the vault is never touched")
        self.assertFalse(any(c[:3] == ["gh", "repo", "delete"] for c in FakeTools.calls))

    def test_dry_run_changes_nothing_and_a_second_uninstall_is_a_no_op(self):
        self.install()
        snap = self.tree()
        self.lines.clear()
        self.assertEqual(self.run_cli(["uninstall", "--dry-run"]), 0)
        self.assertEqual(self.tree(), snap)
        self.assertTrue(any("would remove" in l for l in self.lines))
        self.assertEqual(self.run_cli(["uninstall"]), 0)
        self.lines.clear()
        self.assertEqual(self.run_cli(["uninstall"]), 0)
        self.assertTrue(any("nothing to remove" in l for l in self.lines), self.lines)
        self.assertEqual(self.tree(), self.before)

    def test_unpushed_work_in_the_own_clone_is_kept(self):
        self.install()
        (self.home / "Codes" / "id" / "draft.md").write_text("only here\n", encoding="utf-8")
        self.assertEqual(self.run_cli(["uninstall"]), 0)
        self.assertTrue((self.home / "Codes" / "id" / "draft.md").is_file())
        self.assertTrue(any("kept" in l for l in self.lines), self.lines)

    def test_remote_delete_needs_both_confirmations(self):
        self.install()
        self.assertEqual(self.run_cli(["uninstall", "--delete-remote-repos"]), 1)
        self.assertEqual(self.run_cli(["uninstall", "--delete-remote-repos", "--confirm-remote-delete", "someone"]), 1)
        self.assertEqual(self.run_cli(["uninstall", "--delete-remote-repos", "--confirm-remote-delete", "testperson"]), 1,
                         "without a terminal the last flag is required")
        self.assertFalse(any(c[:3] == ["gh", "repo", "delete"] for c in FakeTools.calls))
        self.assertEqual(self.run_cli(["uninstall", "--delete-remote-repos", "--confirm-remote-delete", "testperson",
                                       "--i-am-sure"]), 0, "\n".join(self.lines))
        deleted = [c[3] for c in FakeTools.calls if c[:3] == ["gh", "repo", "delete"]]
        self.assertEqual(sorted(deleted), ["testperson/ego-teamx", "testperson/id", "testperson/self"])


class RestoreTest(V2):
    """An existing person on a new machine: their self, layers and vault come back."""

    def test_restore_brings_the_whole_setup_back(self):
        me = "restorer"
        idl = make_shared(self.remote, me, "id", {
            "level": "id", "globals": ["me.md"], "rules": [], "dirs": [], "files": []},
            {"global/me.md": "# Me\n\n- my preference\n",
             "tools/unseal.py": "import sys, pathlib\nargs = sys.argv\ninto = pathlib.Path(args[args.index('--into') + 1])\n"
                                "ident = pathlib.Path(args[args.index('--identity') + 1]).read_text()\n"
                                "(into / 'unsealed.txt').write_text('key bytes: %d' % len(ident))\n"})
        manifest = {"id": me, "default_level": "id", "runner": "python", "jobs": ["update"], "layers": [
            {"level": "superego", "path": str(ROOT), "repo": "", "mode": "readonly", "active": True},
            {"level": "collective", "name": "teamx", "company": "teamx", "path": "~/Codes/collective-teamx",
             "repo": self.coll, "mode": "readonly", "active": True},
            {"level": "ego", "name": "teamx", "company": "teamx", "path": "~/Codes/ego-teamx", "repo": self.ego,
             "active": True},
            {"level": "id", "path": "~/Codes/id", "repo": idl, "active": True}]}
        make_shared(self.remote, me, "self", {"level": "x"}, {"manifest.json": json.dumps(manifest)})
        FakeTools.notes["age-identity"] = f"# public key: {RECIPIENT}\n{SECRET}\n"
        rc = self.run_cli(["restore", "--github", me, "--git-host", f"local:{self.remote}", "--jobs", "apply", "--yes"])
        self.assertEqual(rc, 0, "\n".join(self.lines))
        claude = self.home / ".claude"
        self.assertTrue((claude / "me.md").is_file() and (claude / "agent-glossary.md").is_file())
        self.assertIn("my preference", (self.home / ".codex" / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertTrue((claude / "unsealed.txt").is_file(), chr(10).join(self.lines))
        self.assertTrue((claude / "unsealed.txt").read_text(encoding="utf-8").startswith("key bytes:"))
        self.assertNotIn(SECRET, self.all_text() + "\n".join(self.lines))
        self.assertEqual(FakeBackend.installed, {"superego-restorer-update"})
        self.assertFalse(list((self.home / ".local").rglob("age-id*")) if (self.home / ".local").exists() else [],
                         "the temporary identity file is gone")
        self.assertNotIn(CANARY_ID, self.all_text())
        self.assertEqual(self.run_cli(["uninstall"]), 0, "\n".join(self.lines))


if __name__ == "__main__":
    unittest.main()
