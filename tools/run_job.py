"""Run one scheduled job (sync, harvest, weekly) with a log and no console window, on any OS.

Replaces the Windows-only VBScript launcher. The jobs are still bash scripts in this repo until they are ported
to Python, so this finds a usable bash: Git Bash on Windows (never the WSL launcher in System32/WindowsApps),
a bash 4+ on macOS (the system bash is 3.2 and lacks `mapfile`), `bash` elsewhere. The exit code of the job is
the exit code of this program, so the scheduler sees failures.

  python -I tools/run_job.py --manifest MANIFEST sync|harvest|weekly|update

`update` is the one job of a teammate's install (tools/onboard.py update); it is Python and needs no bash.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ospaths  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = {"sync": ("sync.sh", ["--push"]), "harvest": ("harvest.sh", []), "weekly": ("weekly.sh", [])}
LOG_LIMIT = 256 * 1024
MAC_BASH = ("/opt/homebrew/bin/bash", "/usr/local/bin/bash")


def _bad_windows_bash(path: str) -> bool:
    low = path.replace("\\", "/").lower()
    return "/windows/system32/" in low or "/windowsapps/" in low


def find_bash(plat: str | None = None, env: Mapping[str, str] | None = None,
              which: Callable[[str], str | None] = shutil.which,
              exists: Callable[[str], bool] = os.path.isfile) -> str | None:
    e = os.environ if env is None else env
    s = ospaths.system(plat)
    if s == ospaths.WINDOWS:
        cands = []
        for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = e.get(var)
            if base:
                cands.append(os.path.join(base, "Git", "bin", "bash.exe"))
                cands.append(os.path.join(base, "Programs", "Git", "bin", "bash.exe"))
        git = which("git")
        if git:  # <root>\cmd\git.exe or <root>\mingw64\bin\git.exe -> <root>\bin\bash.exe
            root = Path(git).resolve().parent
            for up in (root.parent, root.parent.parent):
                cands.append(str(up / "bin" / "bash.exe"))
        for c in cands:
            if exists(c) and not _bad_windows_bash(c):
                return c
        found = which("bash")
        return found if found and not _bad_windows_bash(found) else None
    if s == ospaths.MACOS:
        for c in MAC_BASH:
            if exists(c):
                return c
    return which("bash")


def bash_major(bash: str, runner: Callable[..., "subprocess.CompletedProcess[str]"] = subprocess.run) -> int | None:
    res = runner([bash, "-c", 'echo "${BASH_VERSINFO[0]}"'], capture_output=True, text=True)
    m = re.search(r"\d+", res.stdout or "")
    return int(m.group()) if res.returncode == 0 and m else None


def rotate(log: Path, limit: int = LOG_LIMIT) -> None:
    if log.exists() and log.stat().st_size > limit:
        old = log.with_name(log.name + ".1")
        if old.exists():
            old.unlink()
        log.rename(old)


def build_command(job: str, bash: str, manifest: Path, repo: Path = REPO) -> list[str]:
    script, extra = SCRIPTS[job]
    return [bash, "-l", (repo / script).as_posix(), *extra, "--manifest", manifest.resolve().as_posix()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job", choices=sorted([*SCRIPTS, "update", "secrets"]))
    ap.add_argument("--manifest", required=True)
    args = ap.parse_args(argv)
    log_dir = ospaths.state_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{args.job}.log"
    rotate(log)
    bash = find_bash() if args.job in SCRIPTS else sys.executable
    with open(log, "ab") as fh:
        if not bash:
            fh.write(f"run_job: no usable bash found for {args.job}\n".encode())
            return 127
        env = dict(os.environ, SYNC_MANIFEST=str(Path(args.manifest).resolve()))
        flags = subprocess.CREATE_NO_WINDOW if ospaths.system() == ospaths.WINDOWS else 0
        if args.job in SCRIPTS:
            cmd = build_command(args.job, bash, Path(args.manifest))
        elif args.job == "update":
            cmd = [sys.executable, "-I", str(REPO / "tools" / "onboard.py"), "update", "--push", "--quiet",
                   "--manifest", str(Path(args.manifest).resolve())]
        else:
            cmd = [sys.executable, "-I", str(REPO / "tools" / "secrets_backup.py"), "run", "--commit", "--push"]
        rc = subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL,
                            stdout=fh, stderr=subprocess.STDOUT, creationflags=flags).returncode
    (log_dir / f"{args.job}.last.json").write_text(
        json.dumps({"exit": rc, "ts": time.strftime("%Y-%m-%d %H:%M")}) + chr(10), encoding="utf-8")
    return rc


if __name__ == "__main__":
    sys.exit(main())
