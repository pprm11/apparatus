#!/usr/bin/env python3
"""Public mirror of the superego: HEAD snapshots without source history, behind the deny gate.

Usage: python -I tools/mirror_public.py [--source REPO] --dry-run [--target DIR]
       python -I tools/mirror_public.py [--source REPO] --target DIR [--publish --remote URL]

Steps: list the tracked files of HEAD, drop the excluded ones (runs/, index/, generated files, the deny
baseline), run the deny gate's own scan (ci/gates.py) on what is left and refuse the whole run on any hit
(exit 2, file and pattern name only, never the matched text). Files the gate allows by path (ci/*, ...) that
still name a deny term are withheld from the mirror instead. Without --dry-run the tree is copied to --target
with a MIRROR.md notice; --publish appends one snapshot commit to remote main and pushes without force.
docs/public-mirror.md has the rules and the commands to create the public repo.
Exit codes: 0 ok, 1 usage or I/O failure, 2 refused by the deny scan.
"""
from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOTICE = "MIRROR.md"
# Machine output and local state that must never be published, whatever is tracked by mistake.
EXCLUDE_DIRS = ("runs/", "index/", ".git/", ".work/", ".harvest/", ".staging/")
EXCLUDE_GLOBS = ("ci/*baseline*", "*.pyc", "*/__pycache__/*")
# Runtime data needed by a public clone. CI implementation, configuration and baselines stay private.
PUBLIC_CI_FILES = frozenset({
    "ci/privacy-terms.json",  # Generic privacy rules used by init, restore and the privacy CLI.
})
NOTICE_TEXT = """# Public mirror

This repository is a mirror of the generic agent-context layer with no source history. Each publish appends
one snapshot commit to the previous mirror commit. This tree comes from source commit `{commit}` on {date}.

Update an existing clone with `git pull --ff-only`.

The mirror accepts no pull requests and no issues. Changes go to the source repository, by invitation.
"""


class Refused(OSError):
    """build() was called with a plan that still has deny hits; nothing was written."""


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses resolve string annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


def _gates():
    return _load("gates", HERE.parent / "ci" / "gates.py")


def _generated_names() -> set[str]:
    sys.path.insert(0, str(HERE.parent / "ci"))
    try:
        return set(_load("repo_gates", HERE.parent / "ci" / "repo_gates.py").GENERATED_NAMES)
    finally:
        sys.path.remove(str(HERE.parent / "ci"))


def git(root: Path, *args: str, check: bool = True) -> bytes:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if check and r.returncode != 0:
        raise OSError(f"git {args[0]} failed: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout


def excluded(rel: str, generated: set[str]) -> bool:
    return (rel.startswith(EXCLUDE_DIRS) or rel.rsplit("/", 1)[-1] in generated
            or (rel.startswith("ci/") and rel not in PUBLIC_CI_FILES)
            or any(fnmatch.fnmatch(rel, g) for g in EXCLUDE_GLOBS))


@dataclass
class Plan:
    commit: str
    files: list[str] = field(default_factory=list)
    withheld: list[str] = field(default_factory=list)
    hits: list[tuple[str, str]] = field(default_factory=list)


def make_plan(source: str | Path) -> Plan:
    """What would be published from the committed tree of `source`. The deny scan is the gate's `scan`,
    run on the HEAD blobs, so an uncommitted edit neither hides nor adds a hit."""
    root = Path(source)
    gates = _gates()
    cfg = json.loads((root / "ci" / "config.json").read_text(encoding="utf-8"))
    deny = cfg.get("denylist", {})
    pats = [(p["name"], gates.re.compile(p["regex"], gates.re.I if p.get("ignore_case", True) else 0))
            for p in deny.get("patterns", [])]

    class HeadCtx(gates.Ctx):
        files = []  # set below; the committed tree, not the index or the working tree

        def read(self, rel: str) -> bytes:
            return git(self.root, "show", f"HEAD:{rel}")

    generated = _generated_names()
    ctx = HeadCtx(root, cfg, False, False, None)
    names = git(root, "ls-tree", "-r", "--name-only", "-z", "HEAD").decode("utf-8").split("\0")
    candidates = sorted(f for f in names if f and not excluded(f, generated))
    # Runtime rules must pass the public scan even though the source gate allows all ci/ files.
    public_runtime = [f for f in candidates if f in PUBLIC_CI_FILES]
    allow = deny.get("allow_paths", [])

    ctx.files = [f for f in candidates if f not in PUBLIC_CI_FILES]
    hits = [(f.path, f.msg.split(" ")[0]) for f in gates.scan(ctx, "deny", pats, allow, skip=gates.DENY_SKIP)]
    ctx.files = public_runtime
    hits += [(f.path, f.msg.split(" ")[0]) for f in gates.scan(ctx, "deny", pats, [])]
    # Allowed by path for the private repo, but not for the public one: such a file that names a term is withheld.
    ctx.files = [f for f in candidates if f not in PUBLIC_CI_FILES and (ctx.match(allow, f) or f in gates.DENY_SKIP)]
    withheld = sorted({f.path for f in gates.scan(ctx, "deny", pats, [])})
    return Plan(commit=git(root, "rev-parse", "HEAD").decode().strip(),
                files=[f for f in candidates if f not in withheld], withheld=withheld, hits=hits)


def build(source: str | Path, target: str | Path, plan: Plan) -> None:
    """Copy the HEAD blobs of the plan to `target`, replacing the previous mirror tree."""
    root, dest = Path(source), Path(target)
    if plan.hits:
        raise Refused("plan has deny hits")
    if dest.exists() and any(dest.iterdir()) and not (dest / NOTICE).is_file():
        raise OSError(f"{dest} is not empty and holds no {NOTICE}; refusing to wipe it")
    if dest.exists():
        for child in dest.iterdir():
            if child.name != ".git":
                shutil.rmtree(child) if child.is_dir() else child.unlink()
    for rel in plan.files:
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(git(root, "show", f"HEAD:{rel}"))
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (dest / NOTICE).write_text(NOTICE_TEXT.format(commit=plan.commit, date=date), encoding="utf-8", newline="\n")


def publish(target: str | Path, remote: str, plan: Plan) -> None:
    """Append a snapshot with remote main as its only parent, then push without force."""
    dest = Path(target)
    git(dest, "init", "-q", "-b", "main")
    parent = remote_head(dest, remote)
    if parent:
        git(dest, "fetch", "-q", "--no-tags", remote, "refs/heads/main")
        parent = git(dest, "rev-parse", "FETCH_HEAD").decode().strip()
    git(dest, "add", "-A")
    tree = git(dest, "write-tree").decode().strip()
    ident = ["-c", "user.name=superego-mirror", "-c", "user.email=mirror@example.com"]
    parents = ["-p", parent] if parent else []
    commit = git(dest, *ident, "commit-tree", tree, *parents, "-m", f"mirror of {plan.commit}").decode().strip()
    git(dest, "update-ref", "refs/heads/main", commit)
    git(dest, "symbolic-ref", "HEAD", "refs/heads/main")
    git(dest, "push", "-q", remote, "refs/heads/main:refs/heads/main")


def remote_head(root: Path, remote: str) -> str | None:
    """Read main without modifying the repo. Missing main is empty; transport errors propagate."""
    refs = git(root, "ls-remote", "--refs", remote, "refs/heads/main").decode().strip()
    return refs.split()[0] if refs else None


def report_refusal(plan: Plan) -> None:
    for path, pattern in plan.hits:
        print(f"REFUSED: {path} {pattern}", file=sys.stderr)
    print(f"REFUSED: {len(plan.hits)} deny hit(s); nothing was written. Clean the source, then run again.",
          file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=str(HERE.parent), help="the superego repo (default: this one)")
    ap.add_argument("--target", help="folder that receives the mirror tree")
    ap.add_argument("--dry-run", action="store_true", help="list what would be published and refused; write nothing")
    ap.add_argument("--publish", action="store_true", help="append a snapshot commit and push it to --remote")
    ap.add_argument("--remote", help="git URL or path of the public repo (with --publish)")
    a = ap.parse_args(argv)
    if not a.dry_run and not a.target:
        ap.error("--target is required unless --dry-run")
    if a.publish and not a.remote:
        print("--publish needs --remote", file=sys.stderr)
        return 1
    try:
        plan = make_plan(a.source)
        for rel in plan.withheld:
            print(f"withheld: {rel} (allowed by path in the private repo, names a deny term)")
        if plan.hits:
            report_refusal(plan)
            return 2
        if a.dry_run:
            print(f"source commit {plan.commit}")
            parent = remote_head(Path(a.source), a.remote) if a.remote else None
            print(f"parent: {parent or 'none'}")
            print(f"would publish {len(plan.files)} file(s):")
            print("\n".join(f"  {rel}" for rel in plan.files))
            return 0
        build(a.source, a.target, plan)
        print(f"mirror tree: {len(plan.files)} file(s) + {NOTICE} in {a.target}")
        if a.publish:
            publish(a.target, a.remote, plan)
            print(f"published one commit to {a.remote}")
    except OSError as exc:
        print(f"mirror: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
