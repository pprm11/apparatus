#!/usr/bin/env python3
"""PostToolUse hook: rebuild the search index when Claude writes a memory, rule or skill (ingest step).

Reads the hook JSON on stdin; does nothing for any other file. Never blocks the session: any error
exits 0 and reports the failure on stderr.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

SEARCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "search_memory.py")
GATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secret_gate.py")


def watched(path: str, root: str) -> bool:
    try:
        parts = Path(os.path.abspath(path)).relative_to(Path(os.path.abspath(root))).parts
    except ValueError:
        return False
    return bool(parts and parts[-1].lower().endswith(".md") and (
        (len(parts) >= 4 and parts[0] == "projects" and parts[2] == "memory")
        or (len(parts) >= 2 and parts[0] in ("rules", "global", "skills"))))


def main() -> None:
    try:
        event = json.load(sys.stdin)
        path = str((event.get("tool_input") or {}).get("file_path") or "")
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from search_memory import resolve_root
        root = resolve_root()
        if watched(path, root):
            if os.environ.get("MEMLIFE_SECRET_GATE") == "1":  # off by default; file:line and kind only, never the value
                gate = subprocess.run([sys.executable, "-I", GATE, path], timeout=10, check=False,
                                      capture_output=True, text=True)
                if gate.returncode == 1:
                    sys.stderr.write(gate.stdout + gate.stderr)
                    sys.exit(2)  # PostToolUse: the write is done; exit 2 shows the message to the agent
            result = subprocess.run([sys.executable, "-I", SEARCH, "--build", "--quiet", "--root", root], timeout=20, check=False,
                                    capture_output=True, text=True)
            if result.returncode:
                sys.stderr.write(f"search index rebuild failed: {result.stderr}")
    except Exception as exc:  # noqa: BLE001 (a hook must never break the session)
        sys.stderr.write(f"search index hook failed: {exc}\n")


if __name__ == "__main__":
    main()
