#!/usr/bin/env python3
"""Local guard against rewriting or deleting the main branch of a layer repo.

GitHub rulesets and branch protection are not available on private repos of a free account, so the layer repos
have no server-side protection. This guard is the local substitute: a git pre-push hook that refuses, for the
protected branches (default `main`):

  * deleting the branch on the remote;
  * a non-fast-forward update (a force push, or a push after a history rewrite).

An ordinary fast-forward push, which is all the hourly sync does, passes. It only covers pushes made from a
clone that has the hook installed; a push from another machine or from the web UI is not seen.

  python -I tools/push_guard.py install <repo>   # write <repo>/.git/hooks/pre-push (idempotent)
  python -I tools/push_guard.py check <remote> <url>   # the hook entry point; reads git's pre-push stdin

Override for a deliberate rewrite: PUSH_GUARD_ALLOW=1 git push ... (the hook prints that it was used).
Protected branches: PUSH_GUARD_BRANCHES="main,release" (comma separated).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

MARKER = "# push_guard.py: managed by superego sync; edit the tool, not this file"
ZERO = "0" * 40
SCRIPT = Path(__file__).resolve()


def protected() -> set[str]:
    raw = os.environ.get("PUSH_GUARD_BRANCHES", "main")
    return {f"refs/heads/{b.strip()}" for b in raw.split(",") if b.strip()}


def is_ancestor(old: str, new: str) -> bool | None:
    """True when `old` is an ancestor of `new`; None when `old` is not in the local object store."""
    have = subprocess.run(["git", "cat-file", "-e", f"{old}^{{commit}}"], capture_output=True)
    if have.returncode != 0:
        return None
    return subprocess.run(["git", "merge-base", "--is-ancestor", old, new], capture_output=True).returncode == 0


def verdict(lines: list[str]) -> list[str]:
    """Reasons to refuse the push described by git's pre-push stdin lines; empty when it may go."""
    prot = protected()
    bad = []
    for ln in lines:
        parts = ln.split()
        if len(parts) != 4:
            continue
        _local_ref, local_sha, remote_ref, remote_sha = parts
        if remote_ref not in prot:
            continue
        name = remote_ref.removeprefix("refs/heads/")
        if local_sha == ZERO:
            bad.append(f"deleting {name} on the remote")
            continue
        if remote_sha == ZERO:
            continue  # creating the branch
        anc = is_ancestor(remote_sha, local_sha)
        if anc is None:
            bad.append(f"{name}: the remote tip {remote_sha[:10]} is not in this clone (git fetch first)")
        elif not anc:
            bad.append(f"{name}: non-fast-forward update (the remote tip {remote_sha[:10]} is not an ancestor)")
    return bad


def check() -> int:
    bad = verdict(sys.stdin.read().splitlines())
    if not bad:
        return 0
    if os.environ.get("PUSH_GUARD_ALLOW") == "1":
        print("push_guard: PUSH_GUARD_ALLOW=1 set, allowing: " + "; ".join(bad), file=sys.stderr)
        return 0
    print("push_guard: push refused.", file=sys.stderr)
    for b in bad:
        print(f"  - {b}", file=sys.stderr)
    print("  History of a layer repo is the backup. For a deliberate rewrite run the push with PUSH_GUARD_ALLOW=1.",
          file=sys.stderr)
    return 1


def hook_text() -> str:
    tool = SCRIPT.as_posix()
    return (
        "#!/bin/sh\n"
        f"{MARKER}\n"
        'py="$(command -v python3 || command -v python)"\n'
        '[ -n "$py" ] || { echo "push_guard: no python on PATH, refusing the push" >&2; exit 1; }\n'
        f'exec "$py" -I "{tool}" check "$@"\n'
    )


def install(repo: Path) -> str:
    git_dir = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-dir"], capture_output=True, text=True)
    if git_dir.returncode != 0:
        return "not a git repo"
    gd = Path(git_dir.stdout.strip())
    gd = gd if gd.is_absolute() else repo / gd
    hook = gd / "hooks" / "pre-push"
    text = hook_text()
    if hook.exists():
        current = hook.read_text(encoding="utf-8", errors="replace")
        if MARKER not in current:
            return f"kept a foreign pre-push hook at {hook}; chain {SCRIPT.name} check by hand"
        if current == text:
            return "already installed"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(text, encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    return f"installed {hook}"


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "check":
        return check()
    if len(argv) == 3 and argv[1] == "install":
        msg = install(Path(argv[2]))
        print(f"push guard: {msg}")
        return 0 if not msg.startswith(("not a git", "kept a foreign")) else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
