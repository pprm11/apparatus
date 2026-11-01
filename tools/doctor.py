"""Green/red checklist of this machine against what the agent context needs, with the OS-specific parts.

  python -I tools/doctor.py [--manifest M] [--json]        exit 1 when any check fails (warnings do not)

`--json` prints {"schema_version": 1, "system": ..., "checks": [{id, status, detail, fix}]}. Status is
`ok`, `warn` or `fail`. Every check is a pure function of an injectable `Env`, so tests need no real tools.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keyfile  # noqa: E402
import ospaths  # noqa: E402
import run_job  # noqa: E402
import scheduler  # noqa: E402

SCHEMA_VERSION = 1
MIN_PYTHON = (3, 10)
AGENTS_MAX = 32 * 1024   # mirrors MAX_BYTES in tools/render_harness.py (Codex stops reading past it)
OK, WARN, FAIL = "ok", "warn", "fail"


@dataclass
class Check:
    id: str
    status: str
    detail: str = ""
    fix: str = ""


@dataclass
class Env:
    plat: str = field(default_factory=lambda: sys.platform)
    env: Mapping[str, str] = field(default_factory=lambda: os.environ)
    home: Path = field(default_factory=Path.home)
    which: Callable[[str], str | None] = shutil.which
    runner: Callable[..., "subprocess.CompletedProcess[str]"] = subprocess.run
    version: tuple[int, int] = field(default_factory=lambda: sys.version_info[:2])

    @property
    def system(self) -> str:
        return ospaths.system(self.plat)

    def run(self, argv: list[str]) -> "subprocess.CompletedProcess[str]":
        try:
            return self.runner(argv, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError) as exc:
            return subprocess.CompletedProcess(argv, 127, "", str(exc))


def check_python(e: Env) -> Check:
    ok = e.version >= MIN_PYTHON
    return Check("python", OK if ok else FAIL, "%d.%d" % e.version,
                 "" if ok else "install Python 3.10+ (the Microsoft Store alias does not count)")


def check_command(e: Env, cmd: str, level: str = FAIL, fix: str = "") -> Check:
    path = e.which(cmd)
    return Check(cmd, OK if path else level, path or "not on PATH", "" if path else fix or f"install {cmd}")


def check_gh_auth(e: Env) -> Check:
    if not e.which("gh"):
        return Check("gh-auth", FAIL, "gh missing", "install gh")
    ok = e.run(["gh", "auth", "status"]).returncode == 0
    return Check("gh-auth", OK if ok else FAIL, "authenticated" if ok else "not logged in",
                 "" if ok else "run bootstrap (token from the vault) or: gh auth login")


def check_bash(e: Env) -> Check:
    bash = run_job.find_bash(e.plat, e.env, e.which)
    if not bash:
        return Check("bash", FAIL, "no usable bash", "install Git for Windows" if e.system == ospaths.WINDOWS
                     else "install bash 4+")
    major = run_job.bash_major(bash, e.runner)
    if e.system != ospaths.WINDOWS and (major is None or major < 4):
        return Check("bash", FAIL, f"{bash} is bash {major}",
                     "brew install bash (the system bash 3.2 lacks mapfile) until the shell jobs are ported")
    return Check("bash", OK, f"{bash} (bash {major})")


def check_dir(e: Env, name: str, path: Path, level: str) -> Check:
    return Check(name, OK if path.is_dir() else level, str(path), "" if path.is_dir() else f"missing: {path}")


def hook_commands(settings: object) -> list[str]:
    """Every `command` string under `hooks` in a settings.json document."""
    out: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "command" and isinstance(v, str):
                    out.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    if isinstance(settings, dict):
        walk(settings.get("hooks", {}))
    return out


def first_token(command: str) -> str:
    c = command.strip()
    if c[:1] in ("'", '"'):
        end = c.find(c[0], 1)
        return c[1:end] if end > 0 else c[1:]
    return c.split(" ", 1)[0]


def check_hooks(e: Env, claude: Path) -> Check:
    path = claude / "settings.json"
    if not path.is_file():
        return Check("hooks", WARN, "no settings.json", "run bootstrap to install the hooks")
    try:
        cmds = hook_commands(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        return Check("hooks", FAIL, f"settings.json unreadable: {exc}")
    bare, missing = [], []
    for c in cmds:
        tok = first_token(c)
        if tok in ("python", "python3", "py") and e.which(tok):
            bare.append(tok)
        elif os.path.isabs(tok) and not os.path.exists(tok):
            missing.append(tok)
        elif not os.path.isabs(tok) and not e.which(tok):
            missing.append(tok)
    if missing:
        return Check("hooks", FAIL, "interpreter not found: " + ", ".join(sorted(set(missing))),
                     "re-run bootstrap so the hooks point at an interpreter that exists")
    if bare:
        return Check("hooks", WARN, "bare interpreter name in a hook (python is python3 on many systems)",
                     "re-run bootstrap: it writes the absolute interpreter path")
    return Check("hooks", OK, f"{len(cmds)} hook command(s)")


def check_agents_md(codex: Path) -> Check:
    f = codex / "AGENTS.md"
    if not f.is_file():
        return Check("agents-md", WARN, "not rendered yet", "python -I tools/render_harness.py")
    size = f.stat().st_size
    pct = size * 100 // AGENTS_MAX
    status = FAIL if size > AGENTS_MAX else WARN if size > AGENTS_MAX * 7 // 8 else OK
    return Check("agents-md", status, f"{size} bytes, {pct}% of the 32 KiB Codex limit")


def check_key_file(e: Env) -> Check:
    path = ospaths.age_dir(e.home) / "id.txt"
    if not path.exists():
        return Check("age-key-file", OK, "no identity on disk (kept in the vault)")
    ok, detail = keyfile.is_private(path, e.plat, e.runner)
    return Check("age-key-file", OK if ok else FAIL, detail, "" if ok else f"restrict it or delete it: {path}")


def check_jobs(e: Env, manifest: Path | None) -> Check:
    if not manifest or not manifest.is_file():
        return Check("jobs", WARN, "no manifest given", "pass --manifest")
    backend_name = scheduler.detect_backend(e.plat, e.which, e.runner)
    be = scheduler.BACKENDS[backend_name](backend_name, runner=e.runner, home=e.home)
    state = be.status(scheduler.jobs_for(manifest, e.plat))
    missing = [n for n, ok in state.items() if not ok]
    if missing:
        return Check("jobs", WARN, f"{backend_name}: not registered: {', '.join(missing)}",
                     f"python -I tools/scheduler.py install --manifest {manifest} --apply")
    return Check("jobs", OK, f"{backend_name}: {len(state)} registered")


def collect(e: Env | None = None, manifest: Path | None = None, profile: str = "full", need_gh: bool = True) -> list[Check]:
    """`profile="person"`: a teammate's install (tools/onboard.py): pure Python, no vault, no bash jobs, no hooks."""
    e = e or Env()
    claude, codex = ospaths.claude_home(e.env, e.home), ospaths.codex_home(e.env, e.home)
    if profile == "person":
        return [
            check_python(e),
            check_command(e, "git", FAIL, "winget/brew/apt install git"),
            check_gh_auth(e) if need_gh else Check("gh-auth", OK, "not needed: no GitHub layer"),
            check_command(e, "claude", WARN, "npm i -g @anthropic-ai/claude-code, then claude /login"),
            check_command(e, "codex", WARN, "optional second harness"),
            check_dir(e, "claude-home", claude, FAIL),
            check_dir(e, "codex-home", codex, WARN),
            check_agents_md(codex),
        ]
    checks = [
        check_python(e),
        check_command(e, "git", FAIL, "winget/brew/apt install git"),
        check_gh_auth(e),
        check_bash(e),
        check_command(e, "bw", WARN, "needed to restore secrets (Bitwarden CLI)"),
        check_command(e, "age", WARN, "needed to open the sealed folder of the personal layer"),
        check_command(e, "claude", WARN, "npm i -g @anthropic-ai/claude-code, then claude /login"),
        check_command(e, "codex", WARN, "optional second harness"),
        check_dir(e, "claude-home", claude, FAIL),
        check_dir(e, "codex-home", codex, WARN),
        check_dir(e, "claude-app-sessions", ospaths.claude_app_sessions(e.plat, e.env, e.home), WARN),
        check_hooks(e, claude),
        check_agents_md(codex),
        check_key_file(e),
        check_jobs(e, manifest),
    ]
    if e.system == ospaths.WINDOWS:
        checks.append(Check("windows-note", OK, "junctions are used for Codex skill links (no admin needed)"))
    return checks


def render(checks: list[Check], plat: str | None = None) -> str:
    mark = {OK: "[ ok ]", WARN: "[warn]", FAIL: "[FAIL]"}
    lines = [f"{mark[c.status]} {c.id}: {c.detail}" + (f"\n         fix: {c.fix}" if c.fix and c.status != OK else "")
             for c in checks]
    bad = sum(c.status == FAIL for c in checks)
    lines.append(f"{len(checks)} checks, {bad} failed, {sum(c.status == WARN for c in checks)} warning(s) on "
                 f"{ospaths.system(plat)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    checks = collect(manifest=Path(args.manifest) if args.manifest else None)
    if args.json:
        print(json.dumps({"schema_version": SCHEMA_VERSION, "system": ospaths.system(),
                          "checks": [asdict(c) for c in checks]}, indent=1))
    else:
        print(render(checks))
    return 1 if any(c.status == FAIL for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
