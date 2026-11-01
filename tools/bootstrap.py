"""Set up a machine for the layered agent context: tools, vault, GitHub auth, layer clones, restore, doctor.

  python -I tools/bootstrap.py --psique OWNER/REPO [--dry-run] [--step NAME ...] [--with-jobs] [--json]

Run through `bootstrap.sh` (macOS, Linux) or `bootstrap.ps1` (Windows), which only find a real Python 3.10+.
Every stage checks before it acts, so a second run changes nothing. The vault login is the only interactive
step of the happy path. What cannot be automated is listed at the end (`MANUAL`). Stages never print a secret.

Stages, in order: packages, vault, auth, repos, restore, jobs (opt-in), doctor.
State goes to `<state dir>/bootstrap-state.json` (schema_version 1). Scheduled jobs are registered only with
`--with-jobs`; the legacy tasks are never touched here.
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
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doctor  # noqa: E402
import layers  # noqa: E402
import ospaths  # noqa: E402
import roots  # noqa: E402
import run_job  # noqa: E402
import scheduler  # noqa: E402

SCHEMA_VERSION = 1
REPO = Path(__file__).resolve().parent.parent
GH_TOKEN_NOTE = "github-token"   # Bitwarden secure note holding a token with contents:write on the layer repos
STAGES = ("packages", "vault", "auth", "repos", "restore", "jobs", "doctor")
MANUAL = (
    "Login to Claude Code (claude /login) and to Codex (codex login): browser OAuth, the jobs use the subscription.",
    "AWS SSO, if used: aws sso login --sso-session <name> (device code in the browser; the config comes from the vault).",
    "Docker Desktop: virtualization, license and possibly a reboot; run bootstrap again afterwards.",
    "The desktop app's scheduled tasks are created inside the Claude app.",
    "OAuth of MCP servers happens on first use (/mcp).",
)


@dataclass(frozen=True)
class Package:
    key: str
    command: str                 # binary whose presence means "installed"
    winget: str | None = None
    brew: str | None = None
    apt: str | None = None
    manual: str = ""             # what to do where no package id is known


PACKAGES: tuple[Package, ...] = (
    Package("git", "git", "Git.Git", "git", "git"),
    Package("python", "python3" if os.name != "nt" else "python", "Python.Python.3.12", "python@3.12", "python3"),
    Package("gh", "gh", "GitHub.cli", "gh", None, "see https://github.com/cli/cli/blob/trunk/docs/install_linux.md"),
    Package("bw", "bw", "Bitwarden.CLI", "bitwarden-cli", None, "npm i -g @bitwarden/cli (or snap install bw)"),
    Package("age", "age", "FiloSottile.age", "age", "age"),
    Package("node", "node", "OpenJS.NodeJS", "node@24", None, "install Node 24 (nodejs.org or a version manager)"),
    Package("uv", "uv", "astral-sh.uv", "uv", None, "pipx install uv, or the installer from astral.sh"),
    Package("aws", "aws", "Amazon.AWSCLI", "awscli", None, "AWS CLI v2 installer from aws.amazon.com"),
    Package("gitleaks", "gitleaks", "Gitleaks.Gitleaks", "gitleaks", None, "release binary from github.com/gitleaks"),
    Package("bun", "bun", "Oven-sh.Bun", "oven-sh/bun/bun", None, "curl installer from bun.sh"),
    Package("docker", "docker", "Docker.DockerDesktop", "--cask docker", None, "docker engine from your distro"),
)
AGENTS = (("claude", "@anthropic-ai/claude-code"), ("codex", "@openai/codex"))


@dataclass
class Result:
    status: str      # ok | skipped | todo | manual | failed
    detail: str = ""


@dataclass
class Runner:
    """Every external command goes through here so tests can record instead of run."""
    dry_run: bool = False
    log: list[list[str]] = field(default_factory=list)

    def run(self, argv: Sequence[str], *, capture: bool = False, text_in: str | None = None,
            interactive: bool = False, check: bool = False) -> "subprocess.CompletedProcess[str]":
        self.log.append(list(argv))
        if self.dry_run:
            return subprocess.CompletedProcess(list(argv), 0, "", "")
        kw: dict = {"text": True, "input": text_in, "check": check}
        if not interactive:
            kw["capture_output"] = True
        elif capture:
            kw["stdout"] = subprocess.PIPE
        return subprocess.run(list(argv), **kw)


@dataclass
class Ctx:
    plat: str
    runner: Runner
    which: Callable[[str], str | None] = shutil.which
    env: dict = field(default_factory=lambda: dict(os.environ))
    manifest: Path | None = None
    psique: str = ""
    home: Path = field(default_factory=Path.home)
    with_jobs: bool = False
    out: Callable[[str], None] = print

    @property
    def system(self) -> str:
        return ospaths.system(self.plat)


def manager(ctx: Ctx) -> str | None:
    if ctx.system == ospaths.WINDOWS:
        return "winget" if ctx.which("winget") else None
    if ctx.system == ospaths.MACOS:
        return "brew" if ctx.which("brew") else None
    return "apt" if ctx.which("apt-get") else None


def install_command(pkg: Package, mgr: str) -> list[str] | None:
    if mgr == "winget" and pkg.winget:
        return ["winget", "install", "--id", pkg.winget, "-e", "--accept-source-agreements",
                "--accept-package-agreements", "--silent"]
    if mgr == "brew" and pkg.brew:
        return ["brew", "install", *pkg.brew.split()]
    if mgr == "apt" and pkg.apt:
        return ["sudo", "apt-get", "install", "-y", pkg.apt]
    return None


def stage_packages(ctx: Ctx) -> Result:
    mgr = manager(ctx)
    missing = [p for p in PACKAGES if not ctx.which(p.command)]
    if not missing:
        return Result("ok", "all tools present")
    failed, manual = [], []
    for p in missing:
        cmd = install_command(p, mgr) if mgr else None
        if cmd is None:
            manual.append(f"{p.key}: {p.manual or 'install it with your package manager'}")
            continue
        if ctx.runner.run(cmd, interactive=True).returncode != 0:
            failed.append(p.key)
    if ctx.which("npm") or ctx.runner.dry_run:
        for cmd_name, npm_pkg in AGENTS:
            if not ctx.which(cmd_name):
                ctx.runner.run(["npm", "install", "-g", npm_pkg], interactive=True)
    notes = (["failed: " + ", ".join(failed)] if failed else []) + (["manual: " + "; ".join(manual)] if manual else [])
    if mgr is None:
        notes.insert(0, "no package manager found (winget, brew or apt-get)")
    if notes:
        return Result("failed" if failed else "manual", " | ".join(notes))
    return Result("ok", f"installed {len(missing)} package(s); open a new shell so PATH picks them up")


def vault_status(ctx: Ctx) -> str:
    res = ctx.runner.run(["bw", "status"])
    try:
        return json.loads(res.stdout or "{}").get("status", "unauthenticated")
    except ValueError:
        return "unauthenticated"


def stage_vault(ctx: Ctx) -> Result:
    if not ctx.which("bw") and not ctx.runner.dry_run:
        return Result("failed", "bw (Bitwarden CLI) is not installed")
    if ctx.env.get("BW_SESSION"):
        return Result("ok", "BW_SESSION already set")
    if ctx.runner.dry_run:
        return Result("todo", "would run: bw login, then bw unlock (master password and 2FA, the only prompt)")
    status = vault_status(ctx)
    if status == "unauthenticated":
        if ctx.runner.run(["bw", "login"], interactive=True).returncode != 0:
            return Result("failed", "bw login did not complete")
        status = "locked"
    if status == "locked":
        res = ctx.runner.run(["bw", "unlock", "--raw"], interactive=True, capture=True)
        token = (res.stdout or "").strip()
        if res.returncode != 0 or not token:
            return Result("failed", "bw unlock did not return a session")
        ctx.env["BW_SESSION"] = token       # this process and its children only; never written to disk
    return Result("ok", "vault unlocked for this run")


def stage_auth(ctx: Ctx) -> Result:
    if ctx.runner.run(["gh", "auth", "status"]).returncode == 0 and not ctx.runner.dry_run:
        ctx.runner.run(["gh", "auth", "setup-git"])
        return Result("ok", "gh already authenticated")
    if ctx.runner.dry_run:
        return Result("todo", f"would read the vault note '{GH_TOKEN_NOTE}' and run: gh auth login --with-token, "
                              "gh auth setup-git")
    if not ctx.env.get("BW_SESSION"):
        return Result("todo", "vault is locked; run the vault stage first")
    got = subprocess.run(["bw", "get", "notes", GH_TOKEN_NOTE, "--session", ctx.env["BW_SESSION"]],
                         capture_output=True, text=True)
    token = got.stdout.strip()
    if got.returncode != 0 or not token:
        return Result("failed", f"vault note '{GH_TOKEN_NOTE}' not found; create it or run: gh auth login")
    login = ctx.runner.run(["gh", "auth", "login", "--with-token"], text_in=token + "\n")
    if login.returncode != 0:
        return Result("failed", "gh auth login --with-token was rejected")
    ctx.runner.run(["gh", "auth", "setup-git"])
    return Result("ok", "gh authenticated from the vault")


_SLUG = re.compile(r"(?:git@github\.com:|https://github\.com/|ssh://git@github\.com/)([^/\s]+/[^/\s]+?)(?:\.git)?/?$")


def repo_slug(url: str) -> str | None:
    """`owner/name` from a GitHub SSH or HTTPS URL (so a clone can go through gh and its token)."""
    m = _SLUG.match(url.strip())
    return m.group(1) if m else (url if re.fullmatch(r"[\w.-]+/[\w.-]+", url) else None)


def clone(ctx: Ctx, slug: str, dest: Path) -> Result:
    if (dest / ".git").exists():
        return Result("ok", f"{dest} already cloned")
    if not ctx.runner.dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
    res = ctx.runner.run(["gh", "repo", "clone", slug, str(dest), "--", "--filter=blob:none"])
    return Result("ok" if res.returncode == 0 else "failed", f"{slug} -> {dest}")


def default_manifest(ctx: Ctx) -> Path:
    return Path(roots.default_manifest())


def stage_repos(ctx: Ctx) -> Result:
    man = ctx.manifest or default_manifest(ctx)
    notes = []
    if not man.is_file():
        if not ctx.psique:
            return Result("failed", f"no manifest at {man}; pass --psique OWNER/REPO or --manifest")
        r = clone(ctx, ctx.psique, man.parent)
        notes.append(r.detail)
        if r.status == "failed":
            return r
    if ctx.runner.dry_run and not man.is_file():
        return Result("todo", f"would clone {ctx.psique}, then every active layer of its manifest")
    data = layers.load_manifest(str(man))
    for layer in layers.active_layers(data):
        slug = repo_slug(layer.get("repo", ""))
        if not slug:
            notes.append(f"{layer['level']}: no repo in the manifest, skipped")
            continue
        r = clone(ctx, slug, Path(layer["path"]))
        notes.append(f"{layer['level']}: {r.status}")
        if r.status == "failed":
            return Result("failed", "; ".join(notes))
    return Result("ok", "; ".join(notes))


def stage_restore(ctx: Ctx) -> Result:
    man = ctx.manifest or default_manifest(ctx)
    script = man.parent / "restore.sh"
    if not script.is_file():
        return Result("todo", f"{script} not found; clone the meta repo first")
    bash = run_job.find_bash(ctx.plat, ctx.env, ctx.which)
    if not bash:
        return Result("failed", "no usable bash to run restore.sh")
    res = ctx.runner.run([bash, script.as_posix(), "--no-clone", "--no-schedule"], interactive=True)
    return Result("ok" if res.returncode == 0 else "failed", "layers restored and composed")


def stage_jobs(ctx: Ctx) -> Result:
    man = ctx.manifest or default_manifest(ctx)
    if not ctx.with_jobs:
        return Result("skipped", f"opt-in: python -I tools/scheduler.py install --manifest {man} --apply")
    if ctx.runner.dry_run:
        return Result("todo", "would register the scheduled jobs for this OS")
    be = scheduler.backend_for()
    names = be.install(scheduler.jobs_for(man, ctx.plat))
    return Result("ok", f"{be.name}: {', '.join(names)}")


def stage_doctor(ctx: Ctx) -> Result:
    checks = doctor.collect(doctor.Env(plat=ctx.plat, home=ctx.home), ctx.manifest)
    failed = [c.id for c in checks if c.status == doctor.FAIL]
    return Result("failed" if failed else "ok", ("failing: " + ", ".join(failed)) if failed else
                  f"{len(checks)} checks passed or warned")


RUNNERS: dict[str, Callable[[Ctx], Result]] = {
    "packages": stage_packages, "vault": stage_vault, "auth": stage_auth, "repos": stage_repos,
    "restore": stage_restore, "jobs": stage_jobs, "doctor": stage_doctor,
}


def load_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") == SCHEMA_VERSION:
            return data
    except (OSError, ValueError):
        pass
    return {"schema_version": SCHEMA_VERSION, "stages": {}}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def run_stages(ctx: Ctx, steps: Sequence[str], state_path: Path | None = None) -> dict[str, Result]:
    state = load_state(state_path) if state_path else {"schema_version": SCHEMA_VERSION, "stages": {}}
    results: dict[str, Result] = {}
    for name in STAGES:
        if name not in steps:
            continue
        try:
            res = RUNNERS[name](ctx)
        except Exception as exc:    # a stage must not stop the ones after it; the state records why
            res = Result("failed", f"{type(exc).__name__}: {exc}")
        results[name] = res
        state["stages"][name] = {"status": res.status, "detail": res.detail,
                                 "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        ctx.out(f"[{res.status:>7}] {name}: {res.detail}")
    if state_path and not ctx.runner.dry_run:
        save_state(state_path, state)
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--psique", default="", help="OWNER/REPO of the meta repo (clone source when no manifest yet)")
    ap.add_argument("--manifest")
    ap.add_argument("--dry-run", action="store_true", help="print what would run; change nothing")
    ap.add_argument("--step", action="append", choices=STAGES, help="run only these stages (repeatable)")
    ap.add_argument("--with-jobs", action="store_true", help="also register the scheduled jobs")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    ctx = Ctx(plat=sys.platform, runner=Runner(dry_run=args.dry_run), psique=args.psique,
              manifest=Path(args.manifest) if args.manifest else None, with_jobs=args.with_jobs)
    if args.json:
        ctx.out = lambda _s: None
    results = run_stages(ctx, args.step or STAGES, ospaths.state_dir() / "bootstrap-state.json")
    if args.json:
        print(json.dumps({"schema_version": SCHEMA_VERSION, "dry_run": args.dry_run,
                          "stages": {k: vars(v) for k, v in results.items()}, "manual": list(MANUAL)}, indent=1))
    else:
        print("\nNot automatable (minimum prompts):")
        for line in MANUAL:
            print(f"  - {line}")
    return 1 if any(r.status == "failed" for r in results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
