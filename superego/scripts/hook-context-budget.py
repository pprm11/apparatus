#!/usr/bin/env python3
"""User's PreToolUse hook (Edit|Write matcher): refuses the edit that takes an always-loaded file (a global, a
rule, a harness adapter or CLAUDE.md under ~/.claude) over the 90% band of its layer's byte budget.

Origin: the rule "always-loaded text has a budget" did not hold because the gate only ran in the hourly sync,
after the text was already in use. Between 2026-10-28 and 2026-10-31 the agent rules file was trimmed twice
and grew back within hours, and the Codex AGENTS.md crossed the 28,672-byte warning line on 2026-10-31. The
arithmetic lives in tools/context_budget.py (check_write); this hook only works out the size the file would
have after the call. Edits made by other means (a shell command, another harness) bypass it; the sync gate
(sync.sh, `--list-band`) is the backstop.

Fails open: any error, a missing manifest or a tools folder without check_write lets the edit through (the
last case is reported on stderr). Shrinking a file always passes. The message for the agent goes to stderr
with exit code 2 (refused). Offline tests: tests/test_context_budget.py in the superego repo (HookTest).

Environment (tests and other layouts): CLAUDE_HOME; SUPEREGO_TOOLS, the folder with context_budget.py and
roots.py (default: the tools/ next to this script's layer folder or one level up, then <layers root>/superego/tools);
CONTEXT_BUDGET_MANIFEST (default: roots.default_manifest, i.e. <layers root>/psique/manifest.json).
"""
import json
import os
import sys

HOME = os.environ.get("CLAUDE_HOME") or os.path.expanduser("~/.claude")
HERE = os.path.dirname(os.path.abspath(__file__))
ALWAYS_LOADED_DIRS = ("rules", "harness")


def tools_dir() -> str | None:
    """First folder that holds context_budget.py: $SUPEREGO_TOOLS, the repo this script lives in, or
    <layers root>/superego/tools (PSIQUE_ROOT, else the usual checkout parent)."""
    up = os.path.dirname(HERE)  # <layer>/scripts -> <layer>; the program's tools/ sit next to the layer or one level up
    candidates = [os.environ.get("SUPEREGO_TOOLS"), os.path.join(up, "tools"), os.path.join(os.path.dirname(up), "tools")]
    root = os.environ.get("PSIQUE_ROOT") or os.path.expanduser("~/Codes")
    candidates.append(os.path.join(root, "superego", "tools"))
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "context_budget.py")):
            return os.path.normpath(c)
    return None


def manifest_path() -> str | None:
    explicit = os.environ.get("CONTEXT_BUDGET_MANIFEST")
    if explicit:
        return explicit
    try:
        import roots  # noqa: E402  (sys.path already holds the tools folder)

        return roots.default_manifest(None)
    except Exception:  # noqa: BLE001
        return None


def maybe_always_loaded(path: str, home: str) -> bool:
    """Cheap prefilter: a .md directly under the home, or under rules/ or harness/. Skills and memory never
    reach the budget, so the hook does not even import the tools for them."""
    rel = os.path.relpath(path, home).replace(os.sep, "/")
    if not rel.endswith(".md"):
        return False
    parts = rel.split("/")
    return len(parts) == 1 or (len(parts) == 2 and parts[0] in ALWAYS_LOADED_DIRS)


def new_size(tool: str, inp: dict, path: str) -> int | None:
    """Bytes the file would have after the call, counted like context_budget.nbytes (LF line ends)."""
    if tool == "Write":
        return len(str(inp.get("content", "")).replace("\r\n", "\n").encode("utf-8"))
    if tool == "Edit":
        try:
            with open(path, encoding="utf-8") as fh:  # universal newlines: CRLF reads as LF
                text = fh.read()
        except OSError:
            return None
        old, new = str(inp.get("old_string", "")), str(inp.get("new_string", ""))
        if not old or old not in text:
            return None
        text = text.replace(old, new) if inp.get("replace_all") else text.replace(old, new, 1)
        return len(text.encode("utf-8"))
    return None


def main() -> int:
    try:
        # -I ignores PYTHONIOENCODING: without this, stdin and stderr follow the console code page (cp1252 on
        # Windows) and accented text in the event is miscounted or fails to match the file.
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        event = json.load(sys.stdin)
        tool = str(event.get("tool_name") or "")
        inp = event.get("tool_input") or {}
        path = str(inp.get("file_path") or "")
        if tool not in ("Edit", "Write") or not path:
            return 0
        home = os.path.normcase(os.path.abspath(HOME))
        target = os.path.normcase(os.path.abspath(path))
        if not target.startswith(home + os.sep) or not maybe_always_loaded(target, home):
            return 0
        tools = tools_dir()
        if tools is None:
            return 0
        sys.path.insert(0, tools)
        manifest = manifest_path()
        if not manifest or not os.path.isfile(manifest):
            return 0
        import context_budget  # noqa: E402

        check = getattr(context_budget, "check_write", None)
        if check is None:
            sys.stderr.write(f"hook-context-budget: {tools} has no check_write; budget gate off for this edit\n")
            return 0
        size = new_size(tool, inp, path)
        if size is None:
            return 0
        message = check(manifest, HOME, path, size)
        if not message:
            return 0
        sys.stderr.write("context budget: " + message + "\n")
        return 2
    except Exception as exc:  # noqa: BLE001 (a hook must never break the session)
        sys.stderr.write(f"hook-context-budget: {exc}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
