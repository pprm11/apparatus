"""Offline tests for the cross-OS layer: ospaths, keyfile, scheduler, run_job, doctor and bootstrap.

Every OS-specific behaviour is a pure function of (platform name, environment, home), so all three systems are
checked on whatever machine runs the suite. Nothing here registers a job, installs a package or touches a real
config folder.
"""
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import bootstrap  # noqa: E402
import doctor  # noqa: E402
import keyfile  # noqa: E402
import ospaths  # noqa: E402
import run_job  # noqa: E402
import scheduler  # noqa: E402

H = Path("hm")   # a relative fake home: joins the same way on every OS and matches no machine-path pattern


def done(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


class Recorder:
    """A subprocess.run stand-in that records argv and answers from a table keyed by argv[0]."""

    def __init__(self, answers=None, default=0):
        self.calls, self.answers, self.default = [], answers or {}, default

    def __call__(self, argv, **kw):
        self.calls.append((list(argv), kw))
        a = self.answers.get(argv[0], self.default)
        return a if isinstance(a, subprocess.CompletedProcess) else done(a)


class OsPaths(unittest.TestCase):
    def test_system_names(self):
        self.assertEqual([ospaths.system(p) for p in ("win32", "darwin", "linux", "cygwin")],
                         ["windows", "macos", "linux", "windows"])

    def test_config_homes_follow_overrides(self):
        self.assertEqual(ospaths.claude_home({}, H), H / ".claude")
        self.assertEqual(ospaths.claude_home({"CLAUDE_CONFIG_DIR": "cfg"}, H), Path("cfg"))
        self.assertEqual(ospaths.codex_home({}, H), H / ".codex")
        self.assertEqual(ospaths.codex_home({"CODEX_HOME": "cx"}, H), Path("cx"))

    def test_app_sessions_per_os(self):
        self.assertEqual(ospaths.claude_app_sessions("win32", {"APPDATA": "ap"}, H),
                         Path("ap") / "Claude" / "claude-code-sessions")
        self.assertEqual(ospaths.claude_app_sessions("win32", {}, H),
                         H / "AppData" / "Roaming" / "Claude" / "claude-code-sessions")
        self.assertEqual(ospaths.claude_app_sessions("darwin", {}, H),
                         H / "Library" / "Application Support" / "Claude" / "claude-code-sessions")
        self.assertEqual(ospaths.claude_app_sessions("linux", {"XDG_CONFIG_HOME": "xc"}, H),
                         Path("xc") / "Claude" / "claude-code-sessions")
        self.assertEqual(ospaths.claude_app_sessions("linux", {}, H),
                         H / ".config" / "Claude" / "claude-code-sessions")

    def test_state_dir_per_os_and_override(self):
        self.assertEqual(ospaths.state_dir("win32", {"LOCALAPPDATA": "la"}, H), Path("la") / "superego")
        self.assertEqual(ospaths.state_dir("darwin", {}, H), H / "Library" / "Application Support" / "superego")
        self.assertEqual(ospaths.state_dir("linux", {"XDG_STATE_HOME": "xs"}, H), Path("xs") / "superego")
        self.assertEqual(ospaths.state_dir("linux", {}, H), H / ".local" / "state" / "superego")
        self.assertEqual(ospaths.state_dir("linux", {"SUPEREGO_HOME": "sh"}, H), Path("sh"))

    def test_codex_exe_path_first_then_windows_app_folder(self):
        self.assertEqual(ospaths.codex_exe("linux", {}, which=lambda _n: "found"), "found")
        hit = ospaths.codex_exe("win32", {"LOCALAPPDATA": "la"}, which=lambda _n: None,
                                globber=lambda pat: [pat.replace("*", "1.0")])
        self.assertTrue(hit.endswith("codex.exe"))
        self.assertIsNone(ospaths.codex_exe("linux", {"LOCALAPPDATA": "la"}, which=lambda _n: None,
                                            globber=lambda _p: ["nope"]))

    def test_gui_interpreter_only_swaps_on_windows(self):
        with tempfile.TemporaryDirectory() as d:
            py, pyw = Path(d) / "python.exe", Path(d) / "pythonw.exe"
            py.write_bytes(b"")
            self.assertEqual(ospaths.gui_interpreter("win32", str(py)), str(py))   # no pythonw next to it
            pyw.write_bytes(b"")
            self.assertEqual(ospaths.gui_interpreter("win32", str(py)), str(pyw))
            self.assertEqual(ospaths.gui_interpreter("linux", str(py)), str(py))


class KeyFile(unittest.TestCase):
    def test_windows_uses_icacls_without_shell(self):
        rec = Recorder()
        with tempfile.TemporaryDirectory() as d:
            p = keyfile.write_private(Path(d) / "k" / "id.txt", "secret", "win32", rec)
            self.assertEqual(p.read_text(), "secret")
        argv, kw = rec.calls[0]
        self.assertEqual(argv[0], "icacls")
        self.assertIn("/inheritance:r", argv)
        self.assertTrue(argv[-1].endswith(":F"))
        self.assertFalse(kw.get("shell"))

    @unittest.skipIf(os.name == "nt", "POSIX mode bits")
    def test_posix_mode_is_owner_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = keyfile.write_private(Path(d) / "id.txt", b"x")
            self.assertEqual(os.stat(p).st_mode & 0o777, 0o600)
            self.assertTrue(keyfile.is_private(p)[0])
            os.chmod(p, 0o644)
            self.assertFalse(keyfile.is_private(p)[0])

    def test_windows_privacy_check_reads_the_acl(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "id.txt"
            p.write_text("x")
            ok = Recorder({"icacls": done(0, f"{p} HOST\\me:(F)\n")})
            bad = Recorder({"icacls": done(0, f"{p} Everyone:(R)\n")})
            self.assertTrue(keyfile.is_private(p, "win32", ok)[0])
            self.assertFalse(keyfile.is_private(p, "win32", bad)[0])

    def test_temp_secret_is_gone_after_the_block(self):
        rec = Recorder()
        with tempfile.TemporaryDirectory() as d:
            with keyfile.temp_secret("abc", d, "age", "win32", rec) as path:
                self.assertEqual(path.read_text(), "abc")
            self.assertFalse(path.exists())


def fake_manifest(d: Path, extra: dict | None = None) -> Path:
    sub = d / "meta"
    sub.mkdir()
    m = sub / "manifest.json"
    m.write_text(json.dumps({"layers": [], **(extra or {})}), encoding="utf-8")
    return m


class SchedulerRendering(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manifest = fake_manifest(Path(self.tmp.name))
        self.jobs = {j.short: j for j in scheduler.jobs_for(self.manifest, "linux", python="py")}

    def test_job_names_come_from_the_manifest(self):
        self.assertEqual(set(self.jobs), {"sync", "harvest", "weekly"})
        self.assertEqual(self.jobs["sync"].name, "superego-meta-sync")
        explicit = Path(self.tmp.name) / "meta" / "manifest.json"
        explicit.write_text(json.dumps({"id": "My Setup!", "layers": []}), encoding="utf-8")
        self.assertEqual(scheduler.jobs_for(explicit, "linux", python="py")[0].name, "superego-my-setup-sync")

    def test_windows_xml_is_well_formed_and_hidden(self):
        for job in self.jobs.values():
            root = ET.fromstring(scheduler.windows_xml(job).split("\n", 1)[1])
            ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
            self.assertEqual(root.find(".//t:Command", ns).text, "py")
            self.assertIn("run_job.py", root.find(".//t:Arguments", ns).text)
            self.assertEqual(root.find(".//t:ExecutionTimeLimit", ns).text, f"PT{job.limit_min}M")
            self.assertEqual(root.find(".//t:StartWhenAvailable", ns).text, "true")
        weekly = ET.fromstring(scheduler.windows_xml(self.jobs["weekly"]).split("\n", 1)[1])
        self.assertIsNotNone(weekly.find(".//{*}Monday"))
        self.assertIsNotNone(ET.fromstring(scheduler.windows_xml(self.jobs["sync"]).split("\n", 1)[1]).find(".//{*}Repetition"))

    def test_launchd_plist(self):
        sync = plistlib.loads(scheduler.launchd_plist(self.jobs["sync"], Path("logs")))
        self.assertEqual(sync["Label"], "ai.superego.superego-meta-sync")
        self.assertEqual(sync["StartCalendarInterval"], {"Minute": 14})
        self.assertEqual(sync["ProgramArguments"][:3], ["py", "-I", str(scheduler.TOOLS / "run_job.py")])
        weekly = plistlib.loads(scheduler.launchd_plist(self.jobs["weekly"], Path("logs")))
        self.assertEqual(weekly["StartCalendarInterval"], {"Weekday": 1, "Hour": 9, "Minute": 0})

    def test_systemd_units(self):
        service, timer = scheduler.systemd_units(self.jobs["harvest"])
        self.assertIn("ExecStart=py -I ", service)
        self.assertIn("TimeoutStartSec=7200", service)
        self.assertIn("OnCalendar=*-*-* *:30:00", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn("OnCalendar=Mon *-*-* 09:00:00", scheduler.systemd_units(self.jobs["weekly"])[1])

    def test_cron_merge_keeps_foreign_lines_and_is_idempotent(self):
        mine = list(self.jobs.values())
        first = scheduler.cron_merge("0 1 * * * backup\n", mine)
        second = scheduler.cron_merge(first, mine)
        self.assertEqual(first, second)
        self.assertIn("0 1 * * * backup", first)
        self.assertEqual(first.count("# superego:superego-meta-sync"), 1)
        self.assertIn("0 9 * * 1 ", first)
        self.assertEqual(scheduler.cron_merge(first, []).strip(), "0 1 * * * backup")

    def test_detect_backend(self):
        self.assertEqual(scheduler.detect_backend("win32"), "windows")
        self.assertEqual(scheduler.detect_backend("darwin"), "launchd")
        self.assertEqual(scheduler.detect_backend("linux", lambda _n: "/bin/systemctl", Recorder(default=0)), "systemd")
        self.assertEqual(scheduler.detect_backend("linux", lambda _n: "/bin/systemctl", Recorder(default=1)), "cron")
        self.assertEqual(scheduler.detect_backend("linux", lambda _n: None, Recorder()), "cron")


class SchedulerBackends(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        self.jobs = scheduler.jobs_for(fake_manifest(d), "linux", python="py")
        self.home, self.logs = d / "home", d / "logs"

    def backend(self, kind, runner):
        return scheduler.BACKENDS[kind](kind, runner=runner, home=self.home, log_dir=self.logs)

    def test_windows_creates_each_task_from_xml(self):
        rec = Recorder()
        names = self.backend("windows", rec).install(self.jobs)
        self.assertEqual(len(names), 3)
        create = [c[0] for c in rec.calls if c[0][1] == "/Create"]
        self.assertEqual([c[3] for c in create], names)
        xml = (self.logs / f"{names[0]}.xml").read_bytes()
        self.assertTrue(xml.startswith(b"\xff\xfe"))

    def test_windows_failure_is_reported(self):
        with self.assertRaises(RuntimeError):
            self.backend("windows", Recorder(default=1)).install(self.jobs)

    def test_legacy_tasks_are_only_removed_on_request(self):
        rec = Recorder()
        be = self.backend("windows", rec)
        be.install(self.jobs)
        self.assertFalse([c for c in rec.calls if c[0][1:2] == ["/Delete"]])
        self.assertEqual(be.remove_legacy(), list(scheduler.LEGACY_TASKS))

    def test_launchd_writes_plists_and_bootstraps(self):
        rec = Recorder()
        self.backend("launchd", rec).install(self.jobs)
        plists = sorted((self.home / "Library" / "LaunchAgents").glob("*.plist"))
        self.assertEqual(len(plists), 3)
        self.assertTrue(any(c[0][:2] == ["launchctl", "bootstrap"] for c in rec.calls))

    def test_systemd_writes_units_enables_timers_and_removes(self):
        rec = Recorder()
        be = self.backend("systemd", rec)
        old = os.environ.pop("XDG_CONFIG_HOME", None)
        try:
            be.install(self.jobs)
            units = list((self.home / ".config" / "systemd" / "user").iterdir())
            self.assertEqual(len(units), 6)
            self.assertTrue(any(c[0][:3] == ["systemctl", "--user", "enable"] for c in rec.calls))
            be.remove(self.jobs)
            self.assertEqual(list((self.home / ".config" / "systemd" / "user").iterdir()), [])
        finally:
            if old is not None:
                os.environ["XDG_CONFIG_HOME"] = old

    def test_cron_roundtrip_through_a_fake_crontab(self):
        store = {"text": "5 5 * * * keep\n"}

        def fake(argv, input=None, **kw):
            if argv == ["crontab", "-l"]:
                return done(0, store["text"])
            store["text"] = input
            return done(0)

        be = self.backend("cron", fake)
        be.install(self.jobs)
        self.assertTrue(all(be.status(self.jobs).values()))
        be.remove(self.jobs)
        self.assertEqual(store["text"].strip(), "5 5 * * * keep")


class RunJob(unittest.TestCase):
    def test_windows_never_picks_the_wsl_launcher(self):
        files = {"gb"}
        got = run_job.find_bash("win32", {"ProgramFiles": "pf"}, which=lambda n: "C:/Windows/System32/bash.exe"
                                if n == "bash" else None, exists=lambda p: False)
        self.assertIsNone(got)
        got = run_job.find_bash("win32", {}, which=lambda n: {"git": os.path.join("gt", "cmd", "git.exe"),
                                                              "bash": None}[n],
                                exists=lambda p: p.replace("\\", "/").endswith("gt/bin/bash.exe") or p in files)
        self.assertTrue(got.replace("\\", "/").endswith("bin/bash.exe"))

    def test_macos_prefers_a_homebrew_bash(self):
        got = run_job.find_bash("darwin", {}, which=lambda n: "/bin/bash", exists=lambda p: p == "/opt/homebrew/bin/bash")
        self.assertEqual(got, "/opt/homebrew/bin/bash")
        self.assertEqual(run_job.find_bash("linux", {}, which=lambda n: "/usr/bin/bash"), "/usr/bin/bash")

    def test_bash_major_parses_the_version(self):
        self.assertEqual(run_job.bash_major("b", Recorder({"b": done(0, "3\n")})), 3)
        self.assertIsNone(run_job.bash_major("b", Recorder({"b": done(1, "")})))

    def test_command_and_log_rotation(self):
        cmd = run_job.build_command("sync", "bash", Path("m.json"), Path("repo"))
        self.assertEqual(cmd[:4], ["bash", "-l", "repo/sync.sh", "--push"])
        self.assertEqual(cmd[-2], "--manifest")
        self.assertNotIn("\\", cmd[2])
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "sync.log"
            log.write_bytes(b"x" * 20)
            run_job.rotate(log, limit=10)
            self.assertFalse(log.exists())
            self.assertTrue((Path(d) / "sync.log.1").exists())


class Doctor(unittest.TestCase):
    def env(self, tmp, plat="linux", present=(), version=(3, 12), runner=None):
        return doctor.Env(plat=plat, env={}, home=Path(tmp), which=lambda n: f"/x/{n}" if n in present else None,
                          runner=runner or Recorder(), version=version)

    def test_python_version_gate(self):
        self.assertEqual(doctor.check_python(self.env("h", version=(3, 9))).status, doctor.FAIL)
        self.assertEqual(doctor.check_python(self.env("h", version=(3, 10))).status, doctor.OK)

    def test_old_bash_fails_on_unix_but_not_on_windows(self):
        rec = Recorder({"/x/bash": done(0, "3\n")})
        self.assertEqual(doctor.check_bash(self.env("h", present=("bash",), runner=rec)).status, doctor.FAIL)
        rec4 = Recorder({"/x/bash": done(0, "5\n")})
        self.assertEqual(doctor.check_bash(self.env("h", present=("bash",), runner=rec4)).status, doctor.OK)

    def test_hooks_flag_bare_and_missing_interpreters(self):
        with tempfile.TemporaryDirectory() as d:
            claude = Path(d)
            settings = lambda cmd: claude.joinpath("settings.json").write_text(  # noqa: E731
                json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": cmd}]}]}}), encoding="utf-8")
            e = self.env(d, present=("python3",))
            settings("python -I script.py")
            self.assertEqual(doctor.check_hooks(e, claude).status, doctor.FAIL)    # `python` not on PATH
            settings("python3 -I script.py")
            self.assertEqual(doctor.check_hooks(e, claude).status, doctor.WARN)    # bare name
            settings(f'"{sys.executable}" -I script.py')
            self.assertEqual(doctor.check_hooks(e, claude).status, doctor.OK)
            settings(os.path.join(d, "missing-python") + " -I s.py")
            self.assertEqual(doctor.check_hooks(e, claude).status, doctor.FAIL)

    def test_agents_md_budget(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "AGENTS.md"
            f.write_bytes(b"a" * 1000)
            self.assertEqual(doctor.check_agents_md(Path(d)).status, doctor.OK)
            f.write_bytes(b"a" * (doctor.AGENTS_MAX + 1))
            self.assertEqual(doctor.check_agents_md(Path(d)).status, doctor.FAIL)

    def test_collect_and_json_shape(self):
        with tempfile.TemporaryDirectory() as d:
            checks = doctor.collect(self.env(d, present=("git", "gh", "bash")))
            ids = [c.id for c in checks]
            self.assertIn("python", ids)
            self.assertIn("claude-app-sessions", ids)
            self.assertTrue(all(c.status in (doctor.OK, doctor.WARN, doctor.FAIL) for c in checks))
            self.assertIn("checks", doctor.render(checks))


class Bootstrap(unittest.TestCase):
    def ctx(self, tmp, plat="linux", present=(), dry=True, **kw):
        return bootstrap.Ctx(plat=plat, runner=bootstrap.Runner(dry_run=dry), which=lambda n: f"/x/{n}" if n in present else None,
                             env={}, home=Path(tmp), out=lambda _s: None, **kw)

    def test_repo_slug_accepts_ssh_https_and_slugs(self):
        for url in ("git@github.com:OWNER/REPO.git", "https://github.com/OWNER/REPO", "https://github.com/OWNER/REPO.git/", "OWNER/REPO"):
            self.assertEqual(bootstrap.repo_slug(url), "OWNER/REPO", url)
        self.assertIsNone(bootstrap.repo_slug("git@example.org:a/b.git"))
        self.assertIsNone(bootstrap.repo_slug(""))

    def test_install_commands_per_manager(self):
        git = next(p for p in bootstrap.PACKAGES if p.key == "git")
        self.assertEqual(bootstrap.install_command(git, "winget")[:3], ["winget", "install", "--id"])
        self.assertEqual(bootstrap.install_command(git, "brew"), ["brew", "install", "git"])
        self.assertEqual(bootstrap.install_command(git, "apt"), ["sudo", "apt-get", "install", "-y", "git"])
        bw = next(p for p in bootstrap.PACKAGES if p.key == "bw")
        self.assertIsNone(bootstrap.install_command(bw, "apt"))
        docker = next(p for p in bootstrap.PACKAGES if p.key == "docker")
        self.assertEqual(bootstrap.install_command(docker, "brew"), ["brew", "install", "--cask", "docker"])

    def test_dry_run_runs_nothing_and_lists_manual_steps(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = self.ctx(d, present=("apt-get",), psique="OWNER/REPO")
            res = bootstrap.run_stages(ctx, bootstrap.STAGES)
            self.assertTrue(ctx.runner.dry_run)
            self.assertEqual(res["vault"].status, "todo")
            self.assertIn("bw login", res["vault"].detail)
            self.assertEqual(res["jobs"].status, "skipped")
            joined = [" ".join(c) for c in ctx.runner.log]
            self.assertTrue(any(c.startswith("sudo apt-get install -y git") for c in joined))
            self.assertFalse(any("--with-token" in c for c in joined))   # a dry run never logs in
        self.assertTrue(bootstrap.MANUAL)

    def test_everything_present_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as d:
            every = tuple(p.command for p in bootstrap.PACKAGES) + ("claude", "codex")
            ctx = self.ctx(d, present=every)
            self.assertEqual(bootstrap.stage_packages(ctx).status, "ok")
            self.assertEqual(ctx.runner.log, [])

    def test_missing_package_manager_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            res = bootstrap.stage_packages(self.ctx(d, plat="darwin", present=()))
            self.assertIn(res.status, ("failed", "manual", "todo"))
            self.assertIn("no package manager", res.detail)

    def test_state_file_roundtrip_and_schema_gate(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s" / "bootstrap-state.json"
            ctx = self.ctx(d, present=tuple(p.command for p in bootstrap.PACKAGES), dry=False)
            res = bootstrap.run_stages(ctx, ("packages", "jobs"), path)
            self.assertEqual(res["packages"].status, "ok")
            state = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(state["schema_version"], 1)
            self.assertEqual(state["stages"]["jobs"]["status"], "skipped")
            path.write_text(json.dumps({"schema_version": 99, "stages": {"x": 1}}), encoding="utf-8")
            self.assertEqual(bootstrap.load_state(path)["stages"], {})

    def test_vault_stage_never_stores_the_session(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = self.ctx(d, present=("bw",), dry=False)
            ctx.env["BW_SESSION"] = "already"
            self.assertEqual(bootstrap.stage_vault(ctx).status, "ok")
            self.assertEqual(ctx.runner.log, [])

    def test_a_failing_stage_does_not_stop_the_next(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = self.ctx(d)
            old = bootstrap.RUNNERS["packages"]
            bootstrap.RUNNERS["packages"] = lambda _c: (_ for _ in ()).throw(ValueError("boom"))
            try:
                res = bootstrap.run_stages(ctx, ("packages", "jobs"))
            finally:
                bootstrap.RUNNERS["packages"] = old
            self.assertEqual(res["packages"].status, "failed")
            self.assertIn("boom", res["packages"].detail)
            self.assertEqual(res["jobs"].status, "skipped")


if __name__ == "__main__":
    unittest.main()
