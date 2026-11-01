#!/usr/bin/env python3
"""Install plain git hooks (no framework needed) that run the gates.

    python ci/install-hooks.py             # write .git/hooks/pre-commit and commit-msg
    python ci/install-hooks.py --force     # replace hooks that were not written by this script
    python -I ci/install-hooks.py check-message FILE   # what the commit-msg hook calls

pre-commit: `python -I ci/gates.py --staged --skip tests` (the unit suite is slow; CI runs it).
commit-msg: the first line must be a Conventional Commits title (gate commit-title).
"""
import stat
import subprocess
import sys
from pathlib import Path

MARK = "# installed by ci/install-hooks.py"
PY = """PY=
for c in python python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys' >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "ci hook: no working python on PATH, so the gates cannot run; install Python or bypass once with --no-verify" >&2; exit 1; }
"""
HOOKS = {
    "pre-commit": f'#!/bin/sh\n{MARK}\n{PY}cd "$(git rev-parse --show-toplevel)" || exit 1\nexec "$PY" -I ci/gates.py --staged --skip tests\n',
    "commit-msg": f'#!/bin/sh\n{MARK}\n{PY}cd "$(git rev-parse --show-toplevel)" || exit 1\nexec "$PY" -I ci/install-hooks.py check-message "$1"\n',
}


def check_message(path: str) -> int:
    lines = [ln for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    title = lines[0] if lines else ""
    if title.startswith(("Merge ", "Revert ", "fixup! ", "squash! ")):
        return 0
    return subprocess.run([sys.executable, "-I", str(Path(__file__).resolve().parent / "gates.py"), "--only", "commit-title", "--title", title]).returncode


def install(force: bool) -> int:
    out = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], capture_output=True, text=True)
    if out.returncode:
        print("not inside a git repository", file=sys.stderr)
        return 1
    hooks = Path(out.stdout.strip())
    hooks.mkdir(parents=True, exist_ok=True)
    for name, body in HOOKS.items():
        target = hooks / name
        if target.exists() and MARK not in target.read_text(encoding="utf-8", errors="replace") and not force:
            print(f"{target} exists and was not written by this script; use --force to replace it", file=sys.stderr)
            return 1
        target.write_text(body, encoding="utf-8", newline="\n")
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["check-message"] and len(sys.argv) == 3:
        sys.exit(check_message(sys.argv[2]))
    sys.exit(install("--force" in sys.argv[1:]))
