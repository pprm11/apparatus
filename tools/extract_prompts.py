#!/usr/bin/env python3
"""Extract the prompts the user typed in Claude Code and Codex sessions since a date, for the weekly pass.

Usage: python -I tools/extract_prompts.py --since 2026-10-11 [--root ~/.claude/projects] [--codex-root '']

Only typed prompts (no tool results, reminders, notifications or meta entries). Long pastes are cut,
secret-looking values are replaced by their type. Output is markdown grouped by project and session.
"""
import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import codex_sessions  # noqa: E402
from redact import redact  # noqa: E402  (single source of redaction rules)

MAX_CHARS = 700
MAX_TOTAL = 80_000
NOISE = ("<command-name", "<local-command", "<task-notification", "<side-sessions-event",
         "<ci-monitor-event", "This session is being continued", "[Request interrupted")
REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)

def parse_ts(ts: str) -> datetime | None:
    """ISO timestamp as an aware datetime, or None when malformed (a bad line must not stop the run)."""
    try:
        when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def is_user_line(line: str) -> bool:
    return '"type":"user"' in line or '"type": "user"' in line


def typed_text(entry: dict) -> str:
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return ""
    content = entry.get("message", {}).get("content")
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return ""
        content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(content, str):
        return ""
    text = REMINDER.sub("", content).strip()
    if not text or text.startswith(NOISE):
        return ""
    return text


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--codex-root", default=codex_sessions.DEFAULT_ROOT, help="'' skips Codex sessions")
    args = ap.parse_args()
    since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)

    by_session: dict[tuple[str, str], list[tuple[str, str]]] = {}
    seen: set[str] = set()

    def add(project: str, session: str, ts: str, text: str) -> None:
        if not text or text in seen:
            return
        seen.add(text)
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + f" [...cut, {len(text)} chars]"
        by_session.setdefault((project, session), []).append((ts[:16], redact(text)))

    if args.codex_root:
        for rec in codex_sessions.iter_records(args.codex_root, since.timestamp()):
            if rec["role"] == "user" and rec["ts"] and (when := parse_ts(rec["ts"])) and when >= since:
                add(rec["proj"], "codex " + rec["sid"][:8], rec["ts"], rec["text"])
    for path in glob.glob(os.path.join(args.root, "*", "*.jsonl")):
        if os.path.getmtime(path) < since.timestamp():
            continue
        project = os.path.basename(os.path.dirname(path))
        session = os.path.basename(path)[:8]
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not is_user_line(line):  # most lines are tool results and assistant turns
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = entry.get("timestamp", "")
                when = parse_ts(ts) if ts else None
                if when is None or when < since:
                    continue
                add(project, session, ts, typed_text(entry))

    out = [f"# Prompts typed since {args.since}\n"]
    size = 0
    for (project, session), prompts in sorted(by_session.items(), key=lambda kv: kv[1][0][0], reverse=True):
        block = [f"\n## {project} · session {session}\n"]
        block += [f"- [{ts}] {text.replace(chr(10), ' / ')}" for ts, text in sorted(prompts)]
        chunk = "\n".join(block)
        if size + len(chunk) > MAX_TOTAL:
            out.append("\n(Output truncated at the size cap: newest sessions first, older ones left out.)")
            break
        out.append(chunk)
        size += len(chunk)
    print("\n".join(out))


if __name__ == "__main__":
    main()
