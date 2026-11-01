#!/usr/bin/env python3
"""Harvest archived sessions (Claude Code and Codex) into memories and skill drafts. harvest.sh drives it.

  python -I tools/harvest.py init                 # mark every session archived so far as seen (no backfill)
  python -I tools/harvest.py pending [--max N]    # archived and not harvested yet, one JSON per line
  python -I tools/harvest.py digest <harness> <id> > digest.md   # redacted transcript digest for the model
  python -I tools/harvest.py mark <harness> <id>  # done (harvested or skipped)

State: ~/.claude/decisions/harvest-state.json. Digests keep only what was said (prompts and replies, no
tool output), redacted with redact.redact (secrets, e-mail, CPF/CNPJ, phone, IP, URL host, long ids), capped at DIGEST_MAX keeping the start and the end.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_sessions  # noqa: E402
import codex_sessions  # noqa: E402
from extract_prompts import typed_text  # noqa: E402
from redact import redact  # noqa: E402

STATE = os.path.expanduser("~/.claude/decisions/harvest-state.json")
DIGEST_MAX = 40_000
TURN_MAX = {"user": 1500, "assistant": 1200}


def load_state(path: str = STATE) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"seen": {}}


def save_state(state: dict, path: str = STATE) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(state, fh, indent=1)
    os.replace(tmp, path)


def key(harness: str, sid: str) -> str:
    return f"{harness}:{sid}"


_SESSIONS: list | None = None


def all_sessions() -> list:
    """agent_sessions.all_sessions() takes 2-3 s; one process asks for it several times, so ask once."""
    global _SESSIONS
    if _SESSIONS is None:
        _SESSIONS = agent_sessions.all_sessions()
    return _SESSIONS


def archived(sessions: list | None = None) -> list:
    sessions = all_sessions() if sessions is None else sessions
    return [s for s in sessions if s.status == "archived" and s.transcript and os.path.isfile(s.transcript)]


def claude_turns(path: str) -> list[tuple[str, str]]:
    turns = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("isSidechain"):
                continue
            if entry.get("type") == "user":
                text = typed_text(entry)
                if text:
                    turns.append(("user", text))
            elif entry.get("type") == "assistant":
                blocks = entry.get("message", {}).get("content")
                if isinstance(blocks, list):
                    text = "\n".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
                    if text.strip():
                        turns.append(("assistant", text.strip()))
    return turns


def digest(session) -> str:
    if session.harness == "claude":
        turns = claude_turns(session.transcript)
    else:
        turns = [(r["role"], r["text"]) for r in codex_sessions.iter_file(session.transcript) if r["role"] in TURN_MAX]
    head = [
        f"# Session digest: {session.title or session.id}",
        f"harness: {session.harness} · id: {session.id} · cwd: {session.cwd}",
        f"memory folder: ~/.claude/projects/{codex_sessions.project_key(session.cwd)}/memory/",
        f"last activity: {time.strftime('%Y-%m-%d', time.localtime(session.last_activity))}",
        "",
    ]
    body = []
    for role, text in turns:
        cap = TURN_MAX[role]
        text = redact(text if len(text) <= cap else text[:cap] + f" [...cut, {len(text)} chars]")
        body.append(f"## {'User' if role == 'user' else 'Agent'}\n{text}\n")
    full = "\n".join(body)
    if len(full) > DIGEST_MAX:
        half = DIGEST_MAX // 2
        full = full[:half] + "\n\n[... middle of the session left out ...]\n\n" + full[-half:]
    return "\n".join(head) + full


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    p_pending = sub.add_parser("pending")
    p_pending.add_argument("--max", type=int, default=6)
    for name in ("digest", "mark"):
        p = sub.add_parser(name)
        p.add_argument("harness", choices=("claude", "codex"))
        p.add_argument("id")
    args = ap.parse_args()

    state = load_state()
    if args.cmd == "init":
        for s in archived():
            state["seen"].setdefault(key(s.harness, s.id), "init")
        save_state(state)
        print(f"{len(state['seen'])} archived sessions marked as seen")
    elif args.cmd == "pending":
        todo = [s for s in archived() if key(s.harness, s.id) not in state["seen"]]
        for s in sorted(todo, key=lambda s: s.last_activity)[: args.max]:
            print(json.dumps({"harness": s.harness, "id": s.id, "title": s.title}, ensure_ascii=False))
    elif args.cmd == "digest":
        match = [s for s in archived() if s.harness == args.harness and s.id == args.id]
        if not match:
            print(f"{args.harness} {args.id}: not an archived session", file=sys.stderr)
            return 1
        print(digest(match[0]))
    elif args.cmd == "mark":
        state["seen"][key(args.harness, args.id)] = time.strftime("%Y-%m-%d %H:%M")
        save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
