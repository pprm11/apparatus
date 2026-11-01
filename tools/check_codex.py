#!/usr/bin/env python3
"""Sensor: does a brand-new Codex session know the user's shared context? Asks a fresh ephemeral, read-only
`codex exec` (no file reads allowed) about facts that exist only in the rendered ~/.codex/AGENTS.md, from a
neutral folder and from each repo given. A miss becomes an item in the decision inbox.

  python -I tools/check_codex.py [--repo DIR ...]     # default repos: canary_repos of the ego layer.json

Run by sync.sh when the rendered AGENTS.md changes, and by weekly.sh. Costs one short Codex turn per folder.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import decisions  # noqa: E402
from common import require_codex  # noqa: E402

QUESTION = ("Do not read any file and do not run any command. Answer only from the instructions you already "
            "have, one line each: (1) the skill names for searching and for saving shared memory; (2) the script "
            "that manages the user's decision inbox; (3) the helper script that sends a child task to the other "
            "harness. If something is not in your instructions, write MISSING.")
# (3) was "the default harness for a child" until B20 (27/10) removed the default: the model and harness
# follow the task, so the adapter's delegate helper is the fact to probe now.
EXPECT = ("context-recall", "context-ingest", "decisions.py", "delegate.py")
def default_repos() -> tuple:
    """Repos to probe, from "canary_repos" of the active ego layer's layer.json (psique manifest); none = neutral only."""
    manifest = os.environ.get("SYNC_MANIFEST", os.path.expanduser("~/Codes/psique/manifest.json"))
    try:
        with open(manifest, encoding="utf-8") as fh:
            layers = json.load(fh)["layers"]
        for layer in layers:
            if layer["level"] == "ego" and layer.get("active", True):
                with open(os.path.join(os.path.expanduser(layer["path"]), "layer.json"), encoding="utf-8") as fh:
                    return tuple(json.load(fh).get("canary_repos", []))
    except (OSError, ValueError, KeyError):
        pass
    return ()


DEFAULT_REPOS = default_repos()


def ask_twice(cwd: str) -> str:
    """A fresh `codex exec` sometimes stalls for minutes without output (seen 26/10 in different folders on
    different runs), so a stall gets one retry before it counts as a miss."""
    return ask(cwd) or ask(cwd)


def ask(cwd: str, timeout: int = 150) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "last.md")
        try:
            # cwd= rather than `-C`: from one repo `-C` ran for 9+ minutes without an answer while
            # the same question from inside the folder answered in seconds (26/10).
            subprocess.run([require_codex(), "exec", "--ephemeral", "--skip-git-repo-check", "-s", "read-only",
                            "-c", "model_reasoning_effort=low", "-o", out, QUESTION],
                           cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return ""
        if not os.path.isfile(out):
            return ""
        with open(out, encoding="utf-8", errors="replace") as fh:
            return fh.read()


def missing(answer: str) -> list[str]:
    low = answer.lower()
    return [token for token in EXPECT if token not in low]


TITLE = "A fresh Codex did not load the shared context"


def raise_item(failures: list[str], home: str = decisions.HOME) -> bool:
    """Add the inbox item unless one with the same title is still open (a failing canary runs hourly)."""
    with decisions.locked(home):
        data = decisions.load(home)
        if any(i["title"] == TITLE and i["status"] == "open" for i in data["items"]):
            return False
        decisions.new_item(
            data, "manual", TITLE, level="ego",
            detail="; ".join(failures) + ". See ~/.codex/AGENTS.md (size, render) and the repo AGENTS.md.",
            options=["A investigate now", "B ignore"], source="tools/check_codex.py")
        decisions.save(data, home)
    return True


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", action="append")
    args = ap.parse_args()
    failures, silent = [], []
    # empty folder: no project AGENTS.md, nothing to scan
    with tempfile.TemporaryDirectory(prefix="codex-canary-") as neutral:
        folders = [neutral] + [os.path.expanduser(r) for r in (args.repo or DEFAULT_REPOS)]
        for folder in folders:
            if not os.path.isdir(folder):
                continue
            answer = ask_twice(folder)
            if not answer.strip():  # no answer says nothing about the context: report, do not raise an item
                silent.append(folder)
                print(f"SKIP {folder}  (no answer in 2 x 150 s; inconclusive)")
                continue
            gaps = missing(answer)
            print(f"{'ok  ' if not gaps else 'FAIL'} {folder}" + (f"  (missing: {', '.join(gaps)})" if gaps else ""))
            if gaps:
                failures.append(f"{folder}: {', '.join(gaps)}")
        if silent and len(silent) == len([f for f in folders if os.path.isdir(f)]):
            failures.append("Codex did not answer in any folder (CLI, login or app-server)")
    if failures:
        raise_item(failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
