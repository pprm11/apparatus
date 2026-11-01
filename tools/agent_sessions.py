"""List the user's agent sessions in both harnesses with a coarse status, for the decision inbox and the harvest.

Claude Code desktop keeps one JSON per session under %APPDATA%/Claude/claude-code-sessions (isArchived,
postTurnSummary, turnWrapUp); its transcript is ~/.claude/projects/<key>/<cliSessionId>.jsonl.
Codex keeps open sessions in ~/.codex/sessions and archived ones in ~/.codex/archived_sessions, with titles
in ~/.codex/session_index.jsonl.

Status: "archived", "waiting" (the agent asked the user something), "done" (last turn completed),
"open" (anything else). Codex logs no status, so "waiting" there means the last assistant message ends in a
question mark: a display hint for the inbox, never used to act on its own.
"""
import glob
import json
import os
import time
from collections.abc import Iterator
from dataclasses import dataclass

CLAUDE_APP = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~/AppData/Roaming")), "Claude", "claude-code-sessions")


def claude_app_dirs() -> list[str]:
    """Where the desktop app keeps its session JSONs. The roaming folder is empty on current builds; the
    sessions live under %LOCALAPPDATA%/Claude-Data/<profile>/claude-code-sessions."""
    local = os.environ.get("LOCALAPPDATA", os.path.expanduser("~/AppData/Local"))
    dirs = [CLAUDE_APP] + sorted(glob.glob(os.path.join(local, "Claude-Data", "*", "claude-code-sessions")))
    return [d for d in dirs if os.path.isdir(d)]


CLAUDE_PROJECTS = os.path.expanduser("~/.claude/projects")
CODEX_HOME = os.path.expanduser("~/.codex")


@dataclass
class Session:
    harness: str
    id: str
    title: str
    cwd: str
    status: str
    last_activity: float  # epoch seconds
    transcript: str
    ask: str = ""

    def idle_days(self, now: float | None = None) -> float:
        return ((now or time.time()) - self.last_activity) / 86400


def _key(cwd: str) -> str:
    return "".join("-" if c in ":\\/" else c for c in cwd.rstrip("\\/"))


def claude_sessions(app_dir: str | list[str] | None = None, projects: str = CLAUDE_PROJECTS) -> Iterator[Session]:
    dirs = claude_app_dirs() if app_dir is None else [app_dir] if isinstance(app_dir, str) else app_dir
    paths = sorted({p for d in dirs for p in glob.glob(os.path.join(d, "*", "*", "*.json"))})
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        summary = d.get("postTurnSummary") or {}
        wrap = d.get("turnWrapUp") or {}
        ask = (wrap.get("ask") or "") if isinstance(wrap, dict) else ""
        if d.get("isArchived"):
            status = "archived"
        elif ask or d.get("interruptedAwaitingPerson") or summary.get("status_category") in ("blocked", "review_ready"):
            status = "waiting"
        elif summary.get("status_category") == "completed":
            status = "done"
        else:
            status = "open"
        cwd = d.get("cwd", "")
        cli = d.get("cliSessionId", "")
        yield Session(
            harness="claude", id=d.get("sessionId", os.path.basename(path)[:-5]), title=d.get("title", ""),
            cwd=cwd, status=status, last_activity=(d.get("lastActivityAt") or d.get("createdAt") or 0) / 1000,
            transcript=os.path.join(projects, _key(cwd), f"{cli}.jsonl") if cli else "", ask=ask,
        )


def _codex_titles(home: str) -> dict[str, str]:
    titles = {}
    try:
        with open(os.path.join(home, "session_index.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                titles[d.get("id", "")] = d.get("thread_name", "")
    except OSError:
        pass
    return titles


TAIL_BYTES = 64 * 1024


def _assistant_text(d: dict) -> str:
    p = d.get("payload")
    if isinstance(p, dict) and p.get("type") == "message" and p.get("role") == "assistant":
        return "\n".join(b.get("text", "") for b in p.get("content") or [] if isinstance(b, dict)).strip()
    return ""


def _codex_tail(path: str) -> tuple[str, str, str]:
    """(session id, cwd, last assistant text) from one rollout file. The session_meta record is the first
    line; the last assistant message is looked for in the final TAIL_BYTES only (rollouts reach hundreds of MB)."""
    sid, cwd, last = "", "", ""
    with open(path, "rb") as fh:
        try:
            first = json.loads(fh.readline().decode("utf-8", errors="replace"))
            if first.get("type") == "session_meta" and isinstance(first.get("payload"), dict):
                sid, cwd = first["payload"].get("id", ""), first["payload"].get("cwd", "")
        except ValueError:
            pass
        size = fh.seek(0, os.SEEK_END)
        fh.seek(max(0, size - TAIL_BYTES))
        chunk = fh.read().decode("utf-8", errors="replace")
    lines = chunk.splitlines()
    if size > TAIL_BYTES:
        lines = lines[1:]  # the first line is cut in the middle
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        last = _assistant_text(d) or last
    return sid, cwd, last


USER_SOURCES = ("vscode", "cli")  # threads the user opened; "exec" and subagent spawns are left out


def _codex_threads(home: str) -> list[tuple] | None:
    """(id, rollout_path, cwd, title, archived, updated_at) from Codex's state DB, read-only; None if absent."""
    path = os.path.join(home, "state_5.sqlite")
    if not os.path.isfile(path):
        return None
    import sqlite3

    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        rows = db.execute(
            "select id, rollout_path, cwd, title, archived, updated_at from threads where source in (?, ?)",
            USER_SOURCES).fetchall()
        db.close()
        return rows
    except sqlite3.Error:
        return None


def _epoch(value: object) -> float:
    if isinstance(value, (int, float)):
        return value / 1000 if value > 1e11 else float(value)
    return 0.0


def codex_sessions(home: str = CODEX_HOME) -> Iterator[Session]:
    """One Session per Codex thread the user opened. The state DB is the source (archive flag, origin);
    without it, fall back to the rollout files."""
    rows = _codex_threads(home)
    if rows is None:
        yield from _codex_sessions_from_files(home)
        return
    titles = _codex_titles(home)
    for sid, rollout, cwd, title, archived, updated in rows:
        last = _codex_tail(rollout)[2] if rollout and os.path.isfile(rollout) else ""
        asks = last.rstrip().endswith("?")
        status = "archived" if archived else ("waiting" if asks else "done" if last else "open")
        when = _epoch(updated) or (os.path.getmtime(rollout) if rollout and os.path.isfile(rollout) else 0)
        yield Session(
            harness="codex", id=sid, title=titles.get(sid) or title or sid, cwd=cwd or "", status=status,
            last_activity=when, transcript=rollout or "", ask=last.strip().splitlines()[-1][:200] if asks else "",
        )


def _codex_sessions_from_files(home: str) -> Iterator[Session]:
    """Fallback: a thread can span several rollout files (resume, compaction) and the newest wins; threads
    without a name in session_index.jsonl are `codex exec` runs or subagents and are left out."""
    titles = _codex_titles(home)
    newest: dict[str, Session] = {}
    for folder, archived in (("sessions", False), ("archived_sessions", True)):
        for path in glob.glob(os.path.join(home, folder, "**", "*.jsonl"), recursive=True):
            sid, cwd, last = _codex_tail(path)
            sid = sid or os.path.basename(path)[:-6]
            if not titles.get(sid):
                continue
            asks = last.rstrip().endswith("?")
            status = "archived" if archived else ("waiting" if asks else "done" if last else "open")
            s = Session(
                harness="codex", id=sid, title=titles[sid], cwd=cwd, status=status,
                last_activity=os.path.getmtime(path), transcript=path,
                ask=last.strip().splitlines()[-1][:200] if asks else "",
            )
            if sid not in newest or s.last_activity > newest[sid].last_activity:
                newest[sid] = s
    yield from newest.values()


def all_sessions() -> list[Session]:
    return list(claude_sessions()) + list(codex_sessions())


if __name__ == "__main__":
    import collections
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    counts = collections.Counter((s.harness, s.status) for s in all_sessions())
    for (harness, status), n in sorted(counts.items()):
        print(f"{harness:7} {status:9} {n}")
