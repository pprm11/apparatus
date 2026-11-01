"""Scheduler abstraction: one job table, four backends (Windows Task Scheduler, launchd, systemd user timers,
cron). Rendering is pure (text in, text out) so it is tested with reference output on any OS; only
`install`, `remove` and `status` touch the system, through an injectable runner.

Job names come from the manifest (`superego-<manifest id>-<job>`), never from code, so two setups on one
machine cannot collide and a rename is a manifest edit.

  python -I tools/scheduler.py plan    --manifest M            # print what would be registered (default)
  python -I tools/scheduler.py install --manifest M --apply    # register for this OS
  python -I tools/scheduler.py remove  --manifest M --apply
  python -I tools/scheduler.py status  --manifest M [--json]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ospaths  # noqa: E402

Runner = Callable[..., "subprocess.CompletedProcess[str]"]
TOOLS = Path(__file__).resolve().parent
MARK = "# superego:"            # cron lines carry this marker plus the job name
LABEL_PREFIX = "ai.superego."   # launchd label prefix
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
SYSTEMD_DAY = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
LEGACY_TASKS = ("ClaudeContextSync", "ClaudeContextHarvest", "ClaudeContextWeekly")


@dataclass(frozen=True)
class Trigger:
    """`hourly` fires every hour at `minute`; `weekly` fires on `weekday` (0 = Monday) at hour:minute."""
    kind: str
    minute: int = 0
    hour: int = 0
    weekday: int = 0


@dataclass(frozen=True)
class Job:
    name: str                 # full registered name
    short: str                # sync | harvest | weekly
    argv: tuple[str, ...]     # command and arguments, already absolute
    trigger: Trigger
    limit_min: int            # kill a hung run after this many minutes
    description: str = ""


# short name -> (trigger, limit in minutes, description). Offsets keep sync and harvest apart.
DEFAULT_JOBS: dict[str, tuple[Trigger, int, str]] = {
    "sync": (Trigger("hourly", minute=14), 45, "Copy the agent context into its layer repos and push"),
    "harvest": (Trigger("hourly", minute=30), 120, "Turn archived sessions into memory drafts"),
    "weekly": (Trigger("weekly", weekday=0, hour=9, minute=0), 120, "Weekly memory maintenance"),
}


# A teammate's install (manifest `"runner": "python"`, tools/onboard.py) has one job and needs no bash.
PERSON_JOBS: dict[str, tuple[Trigger, int, str]] = {
    "update": (Trigger("hourly", minute=20), 45, "Pull the shared layers, recompose, back up your own layer"),
    "secrets": (Trigger("hourly", minute=40), 30, "Encrypt changed secret files into your id layer (age public key)"),
}


def next_run(trigger: Trigger, now: "datetime.datetime") -> "datetime.datetime":
    """First firing strictly after `now` (pure; local time)."""
    if trigger.kind == "hourly":
        t = now.replace(minute=trigger.minute, second=0, microsecond=0)
        return t if t > now else t + datetime.timedelta(hours=1)
    t = now.replace(hour=trigger.hour, minute=trigger.minute, second=0, microsecond=0)
    t += datetime.timedelta(days=(trigger.weekday - now.weekday()) % 7)
    return t if t > now else t + datetime.timedelta(days=7)


def manifest_id(manifest: Path, data: dict | None = None) -> str:
    raw = (data or {}).get("id") or manifest.resolve().parent.name
    return re.sub(r"[^a-z0-9]+", "-", str(raw).lower()).strip("-") or "default"


def jobs_for(manifest: Path, plat: str | None = None, python: str | None = None,
             only: Sequence[str] | None = None, all_jobs: bool = False) -> list[Job]:
    """The job table for this manifest. The command is `<python> -I run_job.py --manifest M <job>`."""
    data = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}
    mid = manifest_id(manifest, data)
    py = python or ospaths.gui_interpreter(plat)
    out = []
    table = PERSON_JOBS if data.get("runner") == "python" else DEFAULT_JOBS
    enabled = None if all_jobs or data.get("runner") != "python" else data.get("jobs")
    for short, (trigger, limit, desc) in table.items():
        if enabled is not None and short not in enabled:
            continue
        if only and short not in only:
            continue
        argv = (py, "-I", str(TOOLS / "run_job.py"), "--manifest", str(manifest.resolve()), short)
        out.append(Job(f"superego-{mid}-{short}", short, argv, trigger, limit, desc))
    return out


# ---------------------------------------------------------------- Windows

def windows_xml(job: Job) -> str:
    """Task Scheduler 1.2 definition. Hidden by construction: the action is `pythonw`, so no console opens."""
    t = job.trigger
    start = f"2026-01-01T{t.hour:02d}:{t.minute:02d}:00"
    if t.kind == "hourly":
        trig = (f"<TimeTrigger><StartBoundary>{start}</StartBoundary><Enabled>true</Enabled>"
                "<Repetition><Interval>PT1H</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>"
                "</TimeTrigger>")
    else:
        trig = (f"<CalendarTrigger><StartBoundary>{start}</StartBoundary><Enabled>true</Enabled>"
                f"<ScheduleByWeek><DaysOfWeek><{WEEKDAYS[t.weekday]}/></DaysOfWeek><WeeksInterval>1</WeeksInterval>"
                "</ScheduleByWeek></CalendarTrigger>")
    args = subprocess.list2cmdline(list(job.argv[1:]))
    return (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        f"  <RegistrationInfo><Description>{escape(job.description)}</Description></RegistrationInfo>\n"
        f"  <Triggers>{trig}</Triggers>\n"
        '  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType>'
        "<RunLevel>LeastPrivilege</RunLevel></Principal></Principals>\n"
        "  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>"
        "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>"
        "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><StartWhenAvailable>true</StartWhenAvailable>"
        f"<ExecutionTimeLimit>PT{job.limit_min}M</ExecutionTimeLimit>"
        "<RestartOnFailure><Interval>PT30M</Interval><Count>2</Count></RestartOnFailure>"
        "<Enabled>true</Enabled></Settings>\n"
        f'  <Actions Context="Author"><Exec><Command>{escape(job.argv[0])}</Command>'
        f"<Arguments>{escape(args)}</Arguments></Exec></Actions>\n"
        "</Task>\n"
    )


# ---------------------------------------------------------------- macOS

def launchd_label(job: Job) -> str:
    return LABEL_PREFIX + job.name


def launchd_plist(job: Job, log_dir: Path) -> bytes:
    t = job.trigger
    cal = {"Minute": t.minute} if t.kind == "hourly" else {"Weekday": (t.weekday + 1) % 7, "Hour": t.hour, "Minute": t.minute}
    body = {
        "Label": launchd_label(job),
        "ProgramArguments": list(job.argv),
        "StartCalendarInterval": cal,
        "StandardOutPath": str(log_dir / f"{job.short}.launchd.log"),
        "StandardErrorPath": str(log_dir / f"{job.short}.launchd.log"),
        "ProcessType": "Background",
    }
    return plistlib.dumps(body, sort_keys=True)


# ---------------------------------------------------------------- Linux

def systemd_units(job: Job) -> tuple[str, str]:
    """(service, timer) unit text. `Persistent=true` runs a missed slot after the machine wakes."""
    cmd = " ".join(shell_quote(a) for a in job.argv)
    service = (f"[Unit]\nDescription={job.description}\n\n[Service]\nType=oneshot\nExecStart={cmd}\n"
               f"TimeoutStartSec={job.limit_min * 60}\n")
    t = job.trigger
    cal = (f"*-*-* *:{t.minute:02d}:00" if t.kind == "hourly"
           else f"{SYSTEMD_DAY[t.weekday]} *-*-* {t.hour:02d}:{t.minute:02d}:00")
    timer = (f"[Unit]\nDescription={job.description}\n\n[Timer]\nOnCalendar={cal}\nPersistent=true\n"
             "\n[Install]\nWantedBy=timers.target\n")
    return service, timer


def shell_quote(arg: str) -> str:
    return arg if re.fullmatch(r"[A-Za-z0-9_@%+=:,./-]+", arg) else "'" + arg.replace("'", "'\\''") + "'"


def cron_line(job: Job) -> str:
    t = job.trigger
    when = f"{t.minute} * * * *" if t.kind == "hourly" else f"{t.minute} {t.hour} * * {(t.weekday + 1) % 7}"
    return f"{when} {' '.join(shell_quote(a) for a in job.argv)} {MARK}{job.name}"


def cron_merge(existing: str, jobs: Sequence[Job], prefix: str = "superego-") -> str:
    """Existing crontab without our lines, plus one fresh line per job. Other people's lines are kept."""
    keep = [ln for ln in existing.splitlines() if (MARK + prefix) not in ln]
    return "\n".join(keep + [cron_line(j) for j in jobs]) + "\n"


# ---------------------------------------------------------------- backends

@dataclass
class Backend:
    name: str
    runner: Runner = subprocess.run
    home: Path = field(default_factory=Path.home)
    log_dir: Path = field(default_factory=lambda: ospaths.state_dir() / "logs")
    applied: list[list[str]] = field(default_factory=list)

    def _run(self, argv: list[str], **kw) -> "subprocess.CompletedProcess[str]":
        self.applied.append(argv)
        return self.runner(argv, capture_output=True, text=True, **kw)

    def install(self, jobs: Sequence[Job]) -> list[str]:
        raise NotImplementedError

    def remove(self, jobs: Sequence[Job]) -> list[str]:
        raise NotImplementedError

    def status(self, jobs: Sequence[Job]) -> dict[str, bool]:
        raise NotImplementedError


class WindowsBackend(Backend):
    def install(self, jobs):
        done = []
        for j in jobs:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            xml = self.log_dir / f"{j.name}.xml"
            xml.write_bytes(b"\xff\xfe" + windows_xml(j).encode("utf-16-le"))
            res = self._run(["schtasks", "/Create", "/TN", j.name, "/XML", str(xml), "/F"])
            if res.returncode != 0:
                raise RuntimeError(f"schtasks create {j.name}: {(res.stderr or res.stdout).strip()}")
            done.append(j.name)
        return done

    def remove(self, jobs):
        return [j.name for j in jobs if self._run(["schtasks", "/Delete", "/TN", j.name, "/F"]).returncode == 0]

    def status(self, jobs):
        return {j.name: self._run(["schtasks", "/Query", "/TN", j.name]).returncode == 0 for j in jobs}

    def remove_legacy(self) -> list[str]:
        return [n for n in LEGACY_TASKS if self._run(["schtasks", "/Delete", "/TN", n, "/F"]).returncode == 0]


class LaunchdBackend(Backend):
    def _dir(self) -> Path:
        return self.home / "Library" / "LaunchAgents"

    def _domain(self) -> str:
        return f"gui/{os.getuid()}" if hasattr(os, "getuid") else "gui/0"

    def install(self, jobs):
        self._dir().mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        done = []
        for j in jobs:
            path = self._dir() / f"{launchd_label(j)}.plist"
            path.write_bytes(launchd_plist(j, self.log_dir))
            self._run(["launchctl", "bootout", f"{self._domain()}/{launchd_label(j)}"])  # idempotent: ignore rc
            res = self._run(["launchctl", "bootstrap", self._domain(), str(path)])
            if res.returncode != 0:
                raise RuntimeError(f"launchctl bootstrap {j.name}: {(res.stderr or res.stdout).strip()}")
            done.append(j.name)
        return done

    def remove(self, jobs):
        out = []
        for j in jobs:
            self._run(["launchctl", "bootout", f"{self._domain()}/{launchd_label(j)}"])
            p = self._dir() / f"{launchd_label(j)}.plist"
            if p.exists():
                p.unlink()
                out.append(j.name)
        return out

    def status(self, jobs):
        return {j.name: self._run(["launchctl", "print", f"{self._domain()}/{launchd_label(j)}"]).returncode == 0
                for j in jobs}


class SystemdBackend(Backend):
    def _dir(self) -> Path:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        return (Path(xdg) if xdg else self.home / ".config") / "systemd" / "user"

    def install(self, jobs):
        self._dir().mkdir(parents=True, exist_ok=True)
        done = []
        for j in jobs:
            service, timer = systemd_units(j)
            (self._dir() / f"{j.name}.service").write_text(service, encoding="utf-8", newline="\n")
            (self._dir() / f"{j.name}.timer").write_text(timer, encoding="utf-8", newline="\n")
            done.append(j.name)
        self._run(["systemctl", "--user", "daemon-reload"])
        for j in jobs:
            res = self._run(["systemctl", "--user", "enable", "--now", f"{j.name}.timer"])
            if res.returncode != 0:
                raise RuntimeError(f"systemctl enable {j.name}: {(res.stderr or res.stdout).strip()}")
        return done

    def remove(self, jobs):
        out = []
        for j in jobs:
            self._run(["systemctl", "--user", "disable", "--now", f"{j.name}.timer"])
            for ext in ("service", "timer"):
                p = self._dir() / f"{j.name}.{ext}"
                if p.exists():
                    p.unlink()
                    out.append(p.name)
        self._run(["systemctl", "--user", "daemon-reload"])
        return out

    def status(self, jobs):
        return {j.name: self._run(["systemctl", "--user", "is-enabled", f"{j.name}.timer"]).returncode == 0
                for j in jobs}


class CronBackend(Backend):
    def _read(self) -> str:
        res = self._run(["crontab", "-l"])
        return res.stdout if res.returncode == 0 else ""

    def _write(self, text: str) -> None:
        self.applied.append(["crontab", "-"])
        res = self.runner(["crontab", "-"], input=text, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"crontab write failed: {(res.stderr or res.stdout).strip()}")

    def install(self, jobs):
        self._write(cron_merge(self._read(), jobs))
        return [j.name for j in jobs]

    def remove(self, jobs):
        self._write(cron_merge(self._read(), []))
        return [j.name for j in jobs]

    def status(self, jobs):
        current = self._read()
        return {j.name: (MARK + j.name) in current for j in jobs}


def detect_backend(plat: str | None = None, which: Callable[[str], str | None] = shutil.which,
                   runner: Runner = subprocess.run) -> str:
    s = ospaths.system(plat)
    if s == ospaths.WINDOWS:
        return "windows"
    if s == ospaths.MACOS:
        return "launchd"
    if which("systemctl"):
        probe = runner(["systemctl", "--user", "show-environment"], capture_output=True, text=True)
        if probe.returncode == 0:
            return "systemd"
    return "cron"


BACKENDS = {"windows": WindowsBackend, "launchd": LaunchdBackend, "systemd": SystemdBackend, "cron": CronBackend}


def backend_for(name: str | None = None, **kw) -> Backend:
    chosen = name or detect_backend()
    return BACKENDS[chosen](chosen, **kw)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("plan", "install", "remove", "status"))
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--backend", choices=sorted(BACKENDS))
    ap.add_argument("--apply", action="store_true", help="touch the system (default: print the plan only)")
    ap.add_argument("--replace-legacy", action="store_true", help="Windows: also delete the old ClaudeContext* tasks")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    jobs = jobs_for(Path(args.manifest))
    be = backend_for(args.backend)
    if args.action == "status":
        st = be.status(jobs)
        print(json.dumps({"schema_version": 1, "backend": be.name, "jobs": st}, indent=1) if args.json
              else "\n".join(f"{n}: {'registered' if ok else 'missing'}" for n, ok in st.items()))
        return 0 if all(st.values()) else 1
    if args.action == "plan" or not args.apply:
        print(f"backend {be.name}; {args.action} would register {len(jobs)} job(s) (add --apply to do it):")
        for j in jobs:
            print(f"  {j.name}: {j.trigger.kind} {j.trigger.hour:02d}:{j.trigger.minute:02d}  {' '.join(j.argv)}")
        return 0
    done = be.install(jobs) if args.action == "install" else be.remove(jobs)
    print(f"{args.action}: {', '.join(done) or 'nothing'}")
    if args.action == "install" and args.replace_legacy and isinstance(be, WindowsBackend):
        print("legacy tasks removed: " + (", ".join(be.remove_legacy()) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
