#!/usr/bin/env python3
"""Keep the live sync checkout on its default branch.

The hourly sync pulls the readonly layers with `pull --ff-only`, so the checkout it runs from must stay on its
upstream default branch. A coding-agent task that uses that checkout as its workspace and commits on its own
branch breaks the next sync (it happened twice on 2026-11-02). This is a git pre-commit hook that refuses a
commit in the main working tree when the branch is not the default branch, and tells the user to use a worktree.

  python -I tools/branch_lock.py install <repo>   # write the pre-commit hook (idempotent, chains an existing one)
  python -I tools/branch_lock.py check            # the hook entry point; run inside the repo

Allowed: SYNC_COMMIT=1 (set by sync.sh and weekly.sh), a linked worktree, a repo without an `origin`, and a
rebase in progress. Never switches branches. A deliberate one-off: SYNC_COMMIT=1 git commit ...
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

MARKER = "# branch_lock.py: managed by superego sync; edit the tool, not this file"
CHAINED = "pre-commit.chained"
SCRIPT = Path(__file__).resolve()


def _git(*args: str, cwd: str | None = None) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    return out.stdout.strip() if out.returncode == 0 else ""


def default_branch(cwd: str | None = None) -> str:
    return _git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=cwd).removeprefix("origin/") or "main"


def refusal(cwd: str | None = None, env: dict | None = None) -> str:
    """The message that refuses this commit, or "" when it may go."""
    if (env if env is not None else os.environ).get("SYNC_COMMIT") == "1":
        return ""
    if not _git("remote", "get-url", "origin", cwd=cwd):
        return ""
    git_dir = Path(_git("rev-parse", "--absolute-git-dir", cwd=cwd))
    common = _git("rev-parse", "--git-common-dir", cwd=cwd)
    common_dir = (Path(cwd or ".") / common).resolve()
    if git_dir.resolve() != common_dir:  # a linked worktree is where tasks belong
        return ""
    if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
        return ""
    default, current = default_branch(cwd), _git("symbolic-ref", "--short", "HEAD", cwd=cwd)
    if current == default:
        return ""
    return (
        f"branch_lock: this is the live sync checkout, which must stay on {default}; the commit is on "
        f"{current or 'a detached HEAD'}. Use a worktree for task work:\n"
        f"  git worktree add ~/Codes/.worktrees/<name> -b <branch> origin/{default}\n"
        f"(one-off exception: SYNC_COMMIT=1 git commit ...)")


def hook_text() -> str:
    return (
        "#!/bin/sh\n"
        f"{MARKER}\n"
        'py="$(command -v python3 || command -v python)"\n'
        '[ -n "$py" ] || { echo "branch_lock: no python on PATH, refusing the commit" >&2; exit 1; }\n'
        f'"$py" -I "{SCRIPT.as_posix()}" check || exit 1\n'
        'chained="$(dirname "$0")/' + CHAINED + '"\n'
        '[ -x "$chained" ] && exec "$chained" "$@"\n'
        "exit 0\n"
    )


def install(repo: Path) -> str:
    hooks = _git("rev-parse", "--git-path", "hooks", cwd=str(repo))  # honors core.hooksPath
    if not hooks:
        return "not a git repo"
    hooks_dir = Path(hooks) if os.path.isabs(hooks) else repo / hooks
    hook, text = hooks_dir / "pre-commit", hook_text()
    note = ""
    if hook.exists():
        current = hook.read_text(encoding="utf-8", errors="replace")
        if MARKER in current:
            if current == text:
                return "already installed"
        else:
            chained = hooks_dir / CHAINED
            if chained.exists():
                return f"kept a foreign pre-commit hook at {hook}; {chained} already exists, chain by hand"
            hook.replace(chained)
            chained.chmod(chained.stat().st_mode | 0o111)
            note = f" (chained the existing hook as {CHAINED})"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook.write_text(text, encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    return f"installed {hook}{note}"


def main(argv: list[str]) -> int:
    if argv[1:2] == ["check"]:
        msg = refusal()
        if msg:
            print(msg, file=sys.stderr)
        return 1 if msg else 0
    if len(argv) == 3 and argv[1] == "install":
        msg = install(Path(argv[2]))
        print(f"branch lock: {msg}")
        return 1 if msg.startswith(("not a git", "kept a foreign")) else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
