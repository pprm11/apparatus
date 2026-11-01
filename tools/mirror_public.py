#!/usr/bin/env python3
"""Public mirror of the superego: the committed tree of HEAD, without history, behind the deny gate.

Usage: python -I tools/mirror_public.py [--source REPO] --dry-run [--target DIR]
       python -I tools/mirror_public.py [--source REPO] --target DIR [--publish --remote URL]

Steps: list the tracked files of HEAD, drop the excluded ones (runs/, index/, generated files, the deny
baseline), run the deny gate's own scan (ci/gates.py) on what is left and refuse the whole run on any hit
(exit 2, file and pattern name only, never the matched text). Files the gate allows by path (ci/*, ...) that
still name a deny term are withheld from the mirror instead. Without --dry-run the tree is copied to --target
with a MIRROR.md notice; --publish then makes one commit there and force-pushes it to --remote (the mirror
has no history). docs/public-mirror.md has the rules and the commands to create the public repo.
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
EXCLUDE_DIRS = ("runs/", "index/", ".git/", ".work/", ".harvest/")
EXCLUDE_GLOBS = ("ci/*baseline*", "*.pyc", "*/__pycache__/*")
NOTICE_TEXT = """# Public mirror

This repository is a mirror of the generic agent-context layer. It has no history: every publish replaces the
tree with one commit, built from source commit `{commit}` on {date}.

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
    allow = deny.get("allow_paths", [])

    ctx.files = candidates
    hits = [(f.path, f.msg.split(" ")[0]) for f in gates.scan(ctx, "deny", pats, allow, skip=gates.DENY_SKIP)]
    # Allowed by path for the private repo, but not for the public one: such a file that names a term is withheld.
    ctx.files = [f for f in candidates if ctx.match(allow, f) or f in gates.DENY_SKIP]
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
    """One commit, no history, force-pushed: the remote tree becomes exactly `target`."""
    dest = Path(target)
    shutil.rmtree(dest / ".git", ignore_errors=True)
    git(dest, "init", "-q", "-b", "main")
    git(dest, "add", "-A")
    ident = ["-c", "user.name=superego-mirror", "-c", "user.email=mirror@example.com"]
    git(dest, *ident, "commit", "-q", "-m", f"mirror of {plan.commit}")
    git(dest, "push", "-q", "--force", remote, "HEAD:main")


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
    ap.add_argument("--publish", action="store_true", help="commit the target and force-push it to --remote")
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
