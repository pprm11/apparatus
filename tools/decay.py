#!/usr/bin/env python3
"""Decay score for memories and skills, from how often and how recently sessions in either harness used them.

Retention R = exp(-t / S), with t = days since last use (or since the file changed, if newer) and
S = BASE_DAYS * (1 + ln(1 + uses)), uses = sessions that touched it (MemoryBank / Ebbinghaus form, with the
log access term of SuperLocalMemory). R < DORMANT goes to the decision inbox; nothing is archived without
the user's answer there. Archiving moves the file to ~/.claude/archive (still in git) and leaves a tombstone.

Never decays: memories of type user or feedback, anything with `pinned: true` in its metadata, skills listed
under "pinned" in ~/.claude/harness/skills.json, rules and schema files (not scanned at all).

  python -I tools/decay.py            # write ~/.claude/decisions/dormant.json and print the table
  python -I tools/decay.py --all      # every item, not only dormant ones
  python -I tools/decay.py --dry-run  # print the dormant ones; write and move nothing

Transcripts are read line by line and cached by (path, mtime, size) in ~/.claude/state/decay-cache.json,
so the weekly run only reads what changed.
"""
import argparse
import glob
import json
import math
import os
import re
import shutil
import sys
import time

HOME = os.path.expanduser("~/.claude")
CODEX = os.path.expanduser("~/.codex")
BASE_DAYS = {"memory": 45.0, "skill": 60.0}
DORMANT = 0.5
WINDOW_DAYS = 180
# Sessions run from the context repos (weekly pass, harvest, maintenance, layer work) read every memory on
# purpose; counting them would mark everything as used. The repos come from the psique manifest (layer paths
# and the meta repo itself), plus CONTEXT_SKIP_PROJECTS (comma-separated project keys) for anything else.
def skip_projects() -> tuple:
    keys = set(filter(None, os.environ.get("CONTEXT_SKIP_PROJECTS", "").split(",")))
    manifest = os.environ.get("SYNC_MANIFEST", os.path.expanduser("~/Codes/psique/manifest.json"))
    try:
        import json
        with open(manifest, encoding="utf-8") as fh:
            paths = [l["path"] for l in json.load(fh)["layers"]] + [os.path.dirname(manifest)]
        for path in paths:
            full = os.path.normpath(os.path.expanduser(path))
            keys.add(re.sub(r"[^A-Za-z0-9]", "-", full))
    except (OSError, ValueError, KeyError):
        pass
    return tuple(sorted(keys))


SKIP_PROJECTS = skip_projects()
SKILL_USE = re.compile(r'"skill"\s*:\s*"(?:[\w-]+:)?([\w-]+)"|skills(?:\\\\|\\|/)+([\w-]+)(?:\\\\|\\|/)+SKILL\.md')
MEMORY_USE = re.compile(r"memory(?:\\\\|\\|/)+([\w-]+)\.md")
FRONT = re.compile(r"^---\n(.*?)\n---", re.S)


def transcripts(home: str = HOME, codex: str = CODEX, window_days: int = WINDOW_DAYS) -> list[str]:
    cutoff = time.time() - window_days * 86400
    paths = [p for p in glob.glob(os.path.join(home, "projects", "*", "*.jsonl"))
             if os.path.basename(os.path.dirname(p)) not in SKIP_PROJECTS]
    for folder in ("sessions", "archived_sessions"):
        paths += glob.glob(os.path.join(codex, folder, "**", "*.jsonl"), recursive=True)
    return [p for p in paths if os.path.getmtime(p) >= cutoff]


CACHE = os.path.join(HOME, "state", "decay-cache.json")


def _names_in(path: str) -> set[tuple[str, str]]:
    """Skill and memory names mentioned in one transcript, read line by line (transcripts reach hundreds of MB)."""
    names: set[tuple[str, str]] = set()
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            names |= {("skill", a or b) for a, b in SKILL_USE.findall(line)}
            names |= {("memory", m) for m in MEMORY_USE.findall(line) if m != "MEMORY"}
    return names


def _load_cache(path: str | None) -> dict:
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def usage(paths: list[str], cache_path: str | None = None, write_cache: bool = True) -> dict[tuple[str, str], tuple[int, float]]:
    """(kind, name) -> (sessions that used it, last use as epoch seconds). With `cache_path`, a transcript
    whose (mtime, size) did not change is not read again: its names come from the cache."""
    out: dict[tuple[str, str], tuple[int, float]] = {}
    cache, fresh = _load_cache(cache_path), {}
    for path in paths:
        try:
            st = os.stat(path)
            when = st.st_mtime
            hit = cache.get(path)
            if hit and hit.get("mtime") == when and hit.get("size") == st.st_size:
                names = {(k, n) for k, n in hit["names"]}
            else:
                names = _names_in(path)
        except OSError:
            continue
        fresh[path] = {"mtime": when, "size": st.st_size, "names": sorted(names)}
        for key in names:
            n, last = out.get(key, (0, 0.0))
            out[key] = (n + 1, max(last, when))
    if cache_path and write_cache and fresh != cache:  # only paths still in the window stay cached
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        tmp = f"{cache_path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(fresh, fh)
        os.replace(tmp, cache_path)
    return out


def frontmatter(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            m = FRONT.match(fh.read().replace("\r\n", "\n"))
    except OSError:
        return ""
    return m.group(1) if m else ""


def changed_at(path: str) -> float:
    """`modified:` from the frontmatter when present: copies by sync and the weekly pass reset the mtime."""
    m = re.search(r"^\s*modified:\s*['\"]?(\d{4}-\d{2}-\d{2})", frontmatter(path), re.M)
    if m:
        return time.mktime(time.strptime(m.group(1), "%Y-%m-%d"))
    return os.path.getmtime(path)


def retention(days: float, uses: int, base: float) -> float:
    return math.exp(-max(days, 0.0) / (base * (1 + math.log1p(uses))))


def items(home: str = HOME) -> list[dict]:
    """Every decayable memory and skill with its path."""
    found = []
    for path in glob.glob(os.path.join(home, "projects", "*", "memory", "*.md")):
        name = os.path.basename(path)[:-3]
        meta = frontmatter(path)
        if name == "MEMORY" or re.search(r"^\s*type:\s*(user|feedback)\s*$", meta, re.M) or re.search(r"^\s*pinned:\s*true", meta, re.M):
            continue
        found.append({"kind": "memory", "name": name, "path": path})
    manifest = os.path.join(home, "harness", "skills.json")
    pinned = set()
    if os.path.isfile(manifest):
        with open(manifest, encoding="utf-8") as fh:
            pinned = set(json.load(fh).get("pinned", []))
    for path in glob.glob(os.path.join(home, "skills", "*", "SKILL.md")):
        name = os.path.basename(os.path.dirname(path))
        if name != "synced" and name not in pinned:
            found.append({"kind": "skill", "name": name, "path": os.path.dirname(path)})
    return found


def score(home: str = HOME, used: dict | None = None, now: float | None = None, dry_run: bool = False) -> list[dict]:
    now = now or time.time()
    used = usage(transcripts(home), os.path.join(home, "state", "decay-cache.json"), write_cache=not dry_run) if used is None else used
    rows = []
    for it in items(home):
        uses, last = used.get((it["kind"], it["name"]), (0, 0.0))
        changed = changed_at(it["path"] if it["kind"] == "memory" else os.path.join(it["path"], "SKILL.md"))
        days = (now - max(last, changed)) / 86400
        rows.append({**it, "uses": uses, "days": round(days, 1),
                     "last_used": time.strftime("%Y-%m-%d", time.localtime(last)) if last else "",
                     "score": round(retention(days, uses, BASE_DAYS[it["kind"]]), 3)})
    return sorted(rows, key=lambda r: r["score"])


def due_for_review(home: str = HOME, now: float | None = None) -> list[dict]:
    """Memories whose `metadata.review_by` date has passed. Read only: it proposes, it never changes a file."""
    now = now or time.time()
    due = []
    for it in items(home):
        if it["kind"] != "memory":
            continue
        m = re.search(r"^\s*review_by:\s*['\"]?(\d{4}-\d{2}-\d{2})", frontmatter(it["path"]), re.M)
        if m and time.mktime(time.strptime(m.group(1), "%Y-%m-%d")) < now:
            due.append({**it, "review_by": m.group(1)})
    return sorted(due, key=lambda r: r["review_by"])


def _tombstone(home: str, line: str) -> None:
    path = os.path.join(home, "archive", "TOMBSTONES.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        if new:
            fh.write("# Archived memories and skills\n\nMove a file back to restore it.\n\n")
        fh.write(line + "\n")


def archive(path: str, what: str, home: str = HOME) -> str:
    if not os.path.exists(path):
        return f"already gone: {path}"
    stamp = time.strftime("%Y-%m-%d")
    if what == "memory":
        project = os.path.basename(os.path.dirname(os.path.dirname(path)))
        dst = os.path.join(home, "archive", "memory", project, os.path.basename(path))
        index = os.path.join(os.path.dirname(path), "MEMORY.md")
        if os.path.isfile(index):
            with open(index, encoding="utf-8") as fh:
                lines = fh.readlines()
            with open(index, "w", encoding="utf-8", newline="") as fh:
                fh.writelines(l for l in lines if f"({os.path.basename(path)})" not in l)
    else:
        dst = os.path.join(home, "archive", "skills", os.path.basename(path))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(path, dst)
    _tombstone(home, f"- {stamp} · {what} `{os.path.basename(path)}` → `{os.path.relpath(dst, home)}`")
    return f"archived {what} {os.path.basename(path)}"


def pin(path: str, what: str, home: str = HOME) -> str:
    if what == "memory":
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        text = re.sub(r"^metadata:\n", "metadata:\n  pinned: true\n", text, count=1, flags=re.M)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    else:
        manifest = os.path.join(home, "harness", "skills.json")
        data = {}
        if os.path.isfile(manifest):
            with open(manifest, encoding="utf-8") as fh:
                data = json.load(fh)
        data["pinned"] = sorted(set(data.get("pinned", [])) | {os.path.basename(path)})
        with open(manifest, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
    return f"pinned {what} {os.path.basename(path)}"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would be offered for archiving; write nothing (no dormant.json, no cache)")
    args = ap.parse_args()
    rows = score(dry_run=args.dry_run)
    dormant = [r for r in rows if r["score"] < DORMANT]
    if not args.dry_run:
        out = os.path.join(HOME, "decisions", "dormant.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(dormant, fh, ensure_ascii=False, indent=1)
    if args.dry_run:
        print(f"dry run, nothing written or moved: {len(dormant)} of {len(rows)} would be offered for archiving (score < {DORMANT})")
        due = due_for_review()
        print(f"{len(due)} memories past `review_by` (listed for review only; no state changes)")
        for r in due:
            print(f"due  {r['review_by']}  {r['name']}")
    else:
        print(f"{len(dormant)} dormant of {len(rows)} (score < {DORMANT})")
    for r in rows if args.all else dormant:
        print(f"{r['score']:.2f}  {r['kind']:6} {r['name']:40} uses={r['uses']:<3} days={r['days']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
