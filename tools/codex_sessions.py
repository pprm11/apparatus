"""Read Codex session logs (~/.codex/sessions/**/*.jsonl) in the shape the Claude readers use.

Codex writes one JSON object per line. Typed prompts are `response_item` messages with role `user`;
the harness also injects user-role messages (AGENTS.md, environment context, app state), which are
dropped here. Used by extract_prompts.py, harvest.py and ~/.claude/scripts/medir-prompts.py.
"""
import glob
import json
import os
import re
from collections.abc import Iterator

DEFAULT_ROOT = os.path.expanduser("~/.codex/sessions")
INJECTED = ("<", "# AGENTS.md instructions")


def project_key(cwd: str) -> str:
    """Same folder key Claude Code uses: every ':', '\\' and '/' of the working directory becomes '-'."""
    cwd = cwd.removeprefix("\\\\?\\")  # Windows extended-length prefix; Claude Code folder keys never have it
    return re.sub(r"[:\\/]", "-", cwd.rstrip("\\/")) if cwd else "codex"


def _texts(content: object, kind: str) -> str:
    if not isinstance(content, list):
        return ""
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == kind)


def iter_records(root: str = DEFAULT_ROOT, min_mtime: float = 0) -> Iterator[dict]:
    """Yield {harness, ts, proj, sid, role, text} for user prompts, assistant replies and compactions."""
    for path in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
        if os.path.getmtime(path) >= min_mtime:
            yield from iter_file(path)


def iter_file(path: str) -> Iterator[dict]:
    """Records of one Codex rollout file."""
    proj, sid = "codex", os.path.basename(path)[:-6]
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            continue
        ts = entry.get("timestamp", "")
        if entry.get("type") == "session_meta":
            proj, sid = project_key(payload.get("cwd", "")), payload.get("id") or sid
            continue
        base = {"harness": "codex", "ts": ts, "proj": proj, "sid": sid}
        if payload.get("type") in ("compacted", "compaction"):
            yield {**base, "role": "compact", "text": ""}
            continue
        if entry.get("type") != "response_item" or payload.get("type") != "message":
            continue
        role = payload.get("role")
        if role == "user":
            text = _texts(payload.get("content"), "input_text").strip()
            if text and not text.startswith(INJECTED):
                yield {**base, "role": "user", "text": text}
        elif role == "assistant":
            text = _texts(payload.get("content"), "output_text").strip()
            if text:
                yield {**base, "role": "assistant", "text": text}
