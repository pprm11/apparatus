#!/usr/bin/env python3
"""Install plain git hooks (no framework) that run the CI gates locally.

    python -I ci/install-hooks.py              # writes .git/hooks/pre-commit and .git/hooks/commit-msg
    python -I ci/install-hooks.py --uninstall  # removes the hooks this script wrote

pre-commit runs `ci/gates.py --staged` with PSIQUE_SKIP_SLOW=1 (`--run-staged`); commit-msg checks the first line for Conventional Commits
(`--check-msg`).
Set PSIQUE_PYTHON to pick the interpreter (default: `python`, then `python3`). Skip once with
`git commit --no-verify` (CI still runs every gate). A hook that was not written by this script is never
overwritten.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

MARK = "# managed by ci/install-hooks.py"

PREAMBLE = """#!/bin/sh
{mark}
set -e
PY="${{PSIQUE_PYTHON:-}}"
[ -n "$PY" ] || PY="$(command -v python || command -v python3 || true)"
[ -n "$PY" ] || {{ echo "ci hook: no python on PATH (set PSIQUE_PYTHON), so the gates cannot run; refusing to continue" >&2; exit 1; }}
cd "$(git rev-parse --show-toplevel)"
"""

HOOKS = {
    "pre-commit": 'exec "$PY" -I ci/install-hooks.py --run-staged\n',
    "commit-msg": 'exec "$PY" -I ci/install-hooks.py --check-msg "$1"\n',
}


def hooks_dir(root: Path) -> Path:
    out = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=root, capture_output=True, text=True,
                         encoding="utf-8", check=True).stdout.strip()
    p = Path(out)
    return p if p.is_absolute() else root / p


def check_msg(root: Path, msg_file: Path) -> int:
    lines = msg_file.read_text(encoding="utf-8", errors="replace").splitlines()
    title = lines[0] if lines else ""
    if title.startswith(("Merge ", "Revert ", "fixup! ", "squash! ")):
        return 0
    return subprocess.run([sys.executable, "-I", str(root / "ci" / "gates.py"), "--only", "commit-title",
                           "--title", title], cwd=root).returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--run-staged", action="store_true",
                    help="run the gates on staged files, skipping the slow restore tests (CI runs them)")
    ap.add_argument("--check-msg", metavar="FILE", help="check the first line of a commit message file")
    a = ap.parse_args(argv)
    root = Path(a.root)
    if a.check_msg:
        return check_msg(root, Path(a.check_msg))
    if a.run_staged:
        return subprocess.run([sys.executable, "-I", str(root / "ci" / "gates.py"), "--staged"], cwd=root,
                              env={**os.environ, "PSIQUE_SKIP_SLOW": "1"}).returncode
    d = hooks_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    rc = 0
    for name, body in HOOKS.items():
        p = d / name
        mine = p.exists() and MARK in p.read_text(encoding="utf-8", errors="replace")
        if a.uninstall:
            if mine:
                p.unlink()
                print(f"removed {p}")
            continue
        if p.exists() and not mine:
            print(f"keeping existing {p} (not written by this script); merge by hand", file=sys.stderr)
            rc = 1
            continue
        p.write_bytes((PREAMBLE.format(mark=MARK) + body).encode("utf-8"))  # LF endings on every OS
        p.chmod(0o755)
        print(f"wrote {p}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
