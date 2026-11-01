#!/usr/bin/env python3
"""The user's decision inbox: one place for every pending decision, shared by Claude Code and Codex.

Store: ~/.claude/decisions/inbox.json (each level synced to its layer repo every hour).
Auto items come from `scan`; any session in either harness adds manual items with `add`.

  python -I tools/decisions.py scan                  # refresh auto items (sessions, proposals, drafts, dormant)
  python -I tools/decisions.py list [--all] [--level L]  # open items as text
  python -I tools/decisions.py add "Title" --detail "..." --options "A merge" "B wait" --source "repo #210" [--level L]
  python -I tools/decisions.py resolve D-12 A [--note "..."]
  python -I tools/decisions.py drop D-12             # no longer relevant
  python -I tools/decisions.py apply                 # carry out resolved actions this script can do
  python -I tools/decisions.py applied D-12          # an agent session carried it out (Claude archive, proposal)
  python -I tools/decisions.py html > page.html      # the central page (published as an artifact)
  python -I tools/decisions.py export --level L      # JSON store with only that level's items, on stdout
  python -I tools/decisions.py import FILE           # merge a store file (newer item wins, next = max)

Levels: superego (general harness), ego (company, the default), id (personal). One store, each level's repo
gets only its items; items without the field count as ego. `--home DIR` (before the command) replaces ~/.claude.
Kinds: session_archive, session_waiting, proposal, skill_draft, dormant_memory, dormant_skill, manual.
Auto items whose cause is gone (session archived, proposal closed) are dropped by `scan`.
"""
import argparse
import contextlib
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_sessions  # noqa: E402
from common import codex_exe  # noqa: E402

HOME = os.path.expanduser("~/.claude")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE_AFTER_DAYS = 3  # a finished session idle this long is offered for archiving
PROPOSAL = re.compile(r"^### (P-[\d-]+) · (.+?)\n(.*?)^Status: (\w+)", re.M | re.S)
KIND_LABEL = {
    "session_waiting": "Session waiting for you",
    "manual": "Decision requested in a session",
    "proposal": "Change proposal",
    "skill_draft": "Skill draft",
    "session_archive": "Session to archive",
    "dormant_memory": "Dormant memory",
    "dormant_skill": "Dormant skill",
}
ORDER = list(KIND_LABEL)
LEVELS = ("superego", "ego", "id")
DEFAULT_LEVEL = "ego"


def store_path(home: str = HOME) -> str:
    return os.path.join(home, "decisions", "inbox.json")


LOCK_WAIT = 10.0   # seconds a writer waits for the lock
LOCK_STALE = 60.0  # a lock file older than this belongs to a dead process


@contextlib.contextmanager
def locked(home: str = HOME):
    """Exclusive lock around a read-modify-write of inbox.json (lock file next to it, created with O_EXCL).
    Every writer takes it, so two sessions cannot overwrite each other or hand out the same D-N."""
    path = store_path(home) + ".lock"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    deadline, delay = time.time() + LOCK_WAIT, 0.02
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except (FileExistsError, PermissionError):
            # Windows raises PermissionError, not FileExistsError, while another process is deleting the lock.
            try:
                if time.time() - os.path.getmtime(path) > LOCK_STALE:
                    os.remove(path)
                    continue
            except OSError:
                continue  # it vanished between the two calls: try again
            if time.time() > deadline:
                raise TimeoutError(f"inbox lock {path} busy for {LOCK_WAIT:.0f} s")
            time.sleep(delay)
            delay = min(delay * 2, 0.5)
    try:
        yield
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def load(home: str = HOME) -> dict:
    try:
        with open(store_path(home), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"next": 1, "items": []}
    return normalize(data)


def normalize(data: dict) -> dict:
    """Old stores have no level: those items belong to ego."""
    for item in data.get("items", []):
        if item.get("level") not in LEVELS:
            item["level"] = DEFAULT_LEVEL
    return data


def save(data: dict, home: str = HOME) -> None:
    path = store_path(home)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def today() -> str:
    return time.strftime("%Y-%m-%d")


def new_item(data: dict, kind: str, title: str, level: str = DEFAULT_LEVEL, **fields: object) -> dict:
    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}, got {level!r}")
    item = {"id": f"D-{data['next']}", "kind": kind, "title": title, "level": level, "detail": "", "options": [],
            "source": "", "key": "", "created": today(), "status": "open", "answer": "", "note": ""}
    item.update(fields)
    data["next"] += 1
    data["items"].append(item)
    return item


def auto_candidates(home: str, sessions: list, now: float) -> dict[str, dict]:
    """key -> fields for every auto item that should be open right now."""
    out: dict[str, dict] = {}
    for s in sessions:
        where = f"{s.harness} · {os.path.basename(s.cwd) or 'no folder'}"
        if s.status == "waiting":
            out[f"waiting:{s.harness}:{s.id}"] = dict(
                kind="session_waiting", level="ego", title=s.title or s.id, detail=s.ask, source=where,
                options=["A I answer in the session", "B archive"], ref={"harness": s.harness, "id": s.id})
        elif s.status == "done" and s.idle_days(now) >= ARCHIVE_AFTER_DAYS:
            out[f"archive:{s.harness}:{s.id}"] = dict(
                kind="session_archive", level="ego", title=s.title or s.id, source=where,
                detail=f"finished, idle for {int(s.idle_days(now))} days",
                options=["A archive", "B keep open"], ref={"harness": s.harness, "id": s.id})
    proposals = os.path.join(REPO, "proposals.md")
    if os.path.isfile(proposals):
        with open(proposals, encoding="utf-8") as fh:
            for pid, title, body, status in PROPOSAL.findall(fh.read()):
                if status == "open":
                    why = re.search(r"^Why: (.+)$", body, re.M)
                    out[f"proposal:{pid}"] = dict(
                        kind="proposal", level="ego", title=f"{pid} · {title}", detail=(why.group(1)[:400] if why else ""),
                        source="ego/proposals.md", options=["A approve", "B reject"], ref={"proposal": pid})
    for skill in sorted(glob.glob(os.path.join(home, "skill-drafts", "*", "SKILL.md"))):
        name = os.path.basename(os.path.dirname(skill))
        out[f"skilldraft:{name}"] = dict(
            kind="skill_draft", title=name, source=os.path.dirname(skill),
            detail="draft created by harvesting an archived session",
            options=["A install", "B discard"], ref={"skill": name})
    dormant = os.path.join(home, "decisions", "dormant.json")
    if os.path.isfile(dormant):
        with open(dormant, encoding="utf-8") as fh:
            for d in json.load(fh):
                out[f"dormant:{d['kind']}:{d['path']}"] = dict(
                    kind=f"dormant_{d['kind']}", title=d["name"], source=d["path"],
                    detail=f"score {d['score']:.2f}, last use {d['last_used'] or 'never seen'}, {d['uses']} uses",
                    options=["A archive (moves to ~/.claude/archive, reversible)", "B keep", "C pin"],
                    ref={"path": d["path"], "what": d["kind"]})
    return out


def scan_stamp_path(home: str = HOME) -> str:
    """The scan time lives outside the synced decisions folder: rewriting it hourly would commit hourly."""
    return os.path.join(home, "state", "decisions-scanned")


def scanned_at(home: str = HOME) -> str:
    try:
        with open(scan_stamp_path(home), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def scan(home: str = HOME, sessions: list | None = None, now: float | None = None) -> tuple[int, int]:
    now = now or time.time()
    # The slow part (listing sessions, ~3 s) runs before load(), so load -> save below is a short
    # window and a concurrent add/resolve/drop is not overwritten.
    wanted = auto_candidates(home, agent_sessions.all_sessions() if sessions is None else sessions, now)
    with locked(home):
        data = load(home)
        by_key = {i["key"]: i for i in data["items"] if i["key"]}
        added = dropped = 0
        changed = data.pop("scanned", None) is not None  # legacy stamp, now kept in state/
        for key, fields in wanted.items():
            if key not in by_key:
                new_item(data, key=key, **fields)
                added += 1
            elif by_key[key]["status"] == "open":
                for k in ("title", "detail", "source"):
                    if k in fields and by_key[key].get(k) != fields[k]:
                        by_key[key][k] = fields[k]
                        changed = True
        for item in data["items"]:
            if item["key"] and item["status"] == "open" and item["key"] not in wanted:
                item.update(status="dropped", note="the cause is gone (archived, answered or closed outside the inbox)")
                dropped += 1
        if added or dropped or changed:
            save(data, home)
    stamp = scan_stamp_path(home)
    os.makedirs(os.path.dirname(stamp), exist_ok=True)
    with open(stamp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(time.strftime("%Y-%m-%d %H:%M"))
    return added, dropped


def find(data: dict, item_id: str) -> dict:
    for item in data["items"]:
        if item["id"].lower() == item_id.lower():
            return item
    raise SystemExit(f"{item_id} not found")


def apply(home: str = HOME) -> list[str]:
    """Carry out resolved items this script can do. Claude session archiving needs the app's own tool,
    so those stay `resolved` for the daily Claude task."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import decay  # noqa: E402  (imported here: decay imports this module's store helpers)

    with locked(home):
        data = load(home)
        log = []
        for item in data["items"]:
            if item["status"] != "resolved" or item.get("applied"):
                continue
            letter = item["answer"][:1].upper()
            ref = item.get("ref", {})
            done = None
            if item["kind"] in ("session_archive", "session_waiting"):
                wants_archive = letter == "A" and item["kind"] == "session_archive" or letter == "B" and item["kind"] == "session_waiting"
                if not wants_archive:
                    done = "nothing to run"
                elif ref.get("harness") == "codex":
                    exe = codex_exe()
                    if exe and subprocess.run([exe, "archive", ref["id"]], capture_output=True).returncode == 0:
                        done = f"codex archive {ref['id']}"
                # Claude sessions stay `resolved`: only the desktop app's own tool can archive them
            elif item["kind"] == "skill_draft":
                src = os.path.join(home, "skill-drafts", ref["skill"])
                if letter == "A" and os.path.isdir(src):
                    shutil.move(src, os.path.join(home, "skills", ref["skill"]))
                    done = f"installed skill {ref['skill']}"
                elif letter == "B" and os.path.isdir(src):
                    shutil.move(src, os.path.join(home, "archive", "skill-drafts", ref["skill"]))
                    done = f"discarded draft {ref['skill']} (kept in ~/.claude/archive)"
            elif item["kind"].startswith("dormant_"):
                if letter == "A":
                    done = decay.archive(ref["path"], ref["what"], home)
                elif letter == "C":
                    done = decay.pin(ref["path"], ref["what"], home)
                else:
                    done = "kept"
            elif item["kind"] == "manual" or (item["kind"] != "proposal" and letter == "B"):
                done = "nothing to run"
            # proposal answers are applied by an agent session ("approve P-..."), which then runs `applied`
            if done:
                item["applied"] = today()
                log.append(f"{item['id']}: {done}")
        if log:
            save(data, home)
        return log


def export_store(data: dict, level: str) -> dict:
    """The part of the store that belongs to one level's repo; `next` is kept so ids never collide on re-import."""
    return {"next": data["next"], "items": [i for i in data["items"] if i["level"] == level]}


def item_stamp(item: dict) -> tuple:
    """Items carry no single 'updated' field: the latest of the dates they were touched, then how far along the
    status is (open < resolved/dropped < applied), so same-day changes still order correctly."""
    dates = [str(item.get(k) or "") for k in ("created", "updated", "resolved", "applied")]
    progress = 2 if item.get("applied") else 1 if item.get("status") in ("resolved", "dropped") else 0
    return max(dates), progress


def import_store(incoming: dict, home: str = HOME) -> tuple[int, int, int]:
    """Merge a store file into the home store by id. Returns (added, updated, unchanged)."""
    normalize(incoming)
    with locked(home):
        data = load(home)
        by_id = {i["id"]: n for n, i in enumerate(data["items"])}
        added = updated = unchanged = 0
        for item in incoming.get("items", []):
            n = by_id.get(item["id"])
            if n is None:
                data["items"].append(item)
                by_id[item["id"]] = len(data["items"]) - 1
                added += 1
            elif item_stamp(item) > item_stamp(data["items"][n]):
                data["items"][n] = item
                updated += 1
            else:
                unchanged += 1
        data["next"] = max(data["next"], incoming.get("next", 1))
        if added or updated or data["next"] != load(home)["next"]:
            save(data, home)
    return added, updated, unchanged


def open_items(data: dict) -> list[dict]:
    items = [i for i in data["items"] if i["status"] == "open"]
    return sorted(items, key=lambda i: (ORDER.index(i["kind"]) if i["kind"] in ORDER else 99, i["created"]))


def render_text(data: dict, show_all: bool = False, scanned: str = "", level: str = "") -> str:
    items = data["items"] if show_all else open_items(data)
    if level:
        items = [i for i in items if i["level"] == level]
    lines = [f"{len(open_items(data))} open · scanned {scanned or data.get('scanned') or 'never'}"]
    for i in items:
        lines.append(f"{i['id']:6} [{i['status']}] ({i['level']}) {KIND_LABEL.get(i['kind'], i['kind'])}: {i['title']}")
        if i["detail"]:
            lines.append(f"       {i['detail'][:160]}")
        if i["options"] and i["status"] == "open":
            lines.append("       " + " | ".join(i["options"]))
    return "\n".join(lines)


CSS = """/* Layout: one reading column, triage order (what blocks the user first), state shown by stripe color */
:root{--bg:#f6f7f9;--card:#ffffff;--fg:#17202b;--muted:#5d6876;--line:#dde2e8;--accent:#1f5fbf;--warn:#9a5208;--warnbg:#fdf3e4;
--sans:"IBM Plex Sans",system-ui,"Segoe UI",sans-serif;--mono:"IBM Plex Mono",ui-monospace,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#13171c;--card:#1b2128;--fg:#e6eaef;--muted:#9aa5b2;--line:#2c343e;--accent:#7eb0f7;--warn:#f2b866;--warnbg:#2e2416;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#13171c;--card:#1b2128;--fg:#e6eaef;--muted:#9aa5b2;--line:#2c343e;--accent:#7eb0f7;--warn:#f2b866;--warnbg:#2e2416;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 var(--sans)}
main{max-width:860px;margin:0 auto;padding-block:24px 48px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
h1{font-size:22px;font-weight:600;margin:0 0 4px;text-wrap:balance}
.sub{color:var(--muted);font-size:13px;margin-bottom:20px}.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:24px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}.stat b{display:block;font-size:22px;font-weight:600}.stat span{color:var(--muted);font-size:12px}
h2{font-size:16px;font-weight:600;margin:26px 0 8px}.item{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:8px 0}
.item.hot{border-color:var(--warn);background:var(--warnbg)}.top{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;min-width:0}.id{font:12px var(--mono);color:var(--accent);font-variant-numeric:tabular-nums}
.t{font-weight:600;overflow-wrap:anywhere}.src{color:var(--muted);font-size:12px}.d{color:var(--muted);font-size:13px;margin-top:4px;overflow-wrap:anywhere}
.opts{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}.opt{font-size:12px;border:1px solid var(--line);border-radius:6px;padding:2px 8px}
.how{color:var(--muted);font-size:13px;border-top:1px solid var(--line);margin-top:28px;padding-top:12px}code{font:12px var(--mono);overflow-wrap:anywhere}"""
FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono&'
         'family=IBM+Plex+Sans:wght@400;600&display=swap">')


def render_html(data: dict, scanned: str = "") -> str:
    all_open = open_items(data)
    # The page is published on claude.ai: personal (id) items only show as a count, never in detail.
    personal = sum(1 for i in all_open if i["level"] == "id")
    items = [i for i in all_open if i["level"] != "id"]
    esc = html.escape
    level_stats = "".join(f'<div class="stat"><b>{n}</b><span>{lv}</span></div>'
                          for lv in LEVELS if lv != "id" and (n := sum(1 for i in items if i["level"] == lv)))
    counts = {k: sum(1 for i in items if i["kind"] == k) for k in ORDER}
    stats = level_stats + "".join(f'<div class="stat"><b>{counts[k]}</b><span>{esc(KIND_LABEL[k])}</span></div>' for k in ORDER if counts[k])
    body = []
    for kind in ORDER:
        group = [i for i in items if i["kind"] == kind]
        if not group:
            continue
        body.append(f"<h2>{esc(KIND_LABEL[kind])} ({len(group)})</h2>")
        for i in group:
            hot = " hot" if kind in ("session_waiting", "manual") else ""
            lvl = f' · {esc(i["level"])}' 
            opts = "".join(f'<span class="opt">{esc(o)}</span>' for o in i["options"])
            body.append(
                f'<div class="item{hot}"><div class="top"><span class="id">{esc(i["id"])}</span>'
                f'<span class="t">{esc(i["title"])}</span><span class="src">{esc(i["source"])}{lvl} · since {esc(i["created"])}</span></div>'
                + (f'<div class="d">{esc(i["detail"])}</div>' if i["detail"] else "")
                + (f'<div class="opts">{opts}</div>' if opts else "") + "</div>")
    if personal:
        body.append(f'<p class="sub">{personal} personal decisions, see the session.</p>')
    if not all_open:
        body.append('<p class="sub">Nothing pending.</p>')
    # Artifact page contract: no doctype/html/head/body of our own; the publisher wraps the page.
    return f"""<title>Decision inbox</title>
<meta name="claude:viewport-fit-sides" content="cover">
{FONTS}<style>{CSS}</style><main lang="en">
<h1>Decision inbox</h1><div class="sub">{len(all_open)} pending · updated {esc(scanned or data.get('scanned', ''))} · Claude Code and Codex</div>
<div class="stats">{stats}</div>{''.join(body)}
<div class="how">To decide, say in any session (Claude or Codex): <code>resolve D-12 A</code>, or several at once
(<code>D-3 A, D-7 B</code>). The daily 09:00 task asks too. Command: <code>python -I ~/Codes/superego/tools/decisions.py</code></div>
</main>
"""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=HOME, help="replaces ~/.claude (tests)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    p_list = sub.add_parser("list")
    p_list.add_argument("--all", action="store_true")
    p_list.add_argument("--level", choices=LEVELS)
    p_add = sub.add_parser("add")
    p_add.add_argument("title")
    p_add.add_argument("--detail", default="")
    p_add.add_argument("--options", nargs="*", default=[])
    p_add.add_argument("--source", default="")
    p_add.add_argument("--level", choices=LEVELS, default=DEFAULT_LEVEL)
    p_res = sub.add_parser("resolve")
    p_res.add_argument("id")
    p_res.add_argument("answer")
    p_res.add_argument("--note", default="")
    p_drop = sub.add_parser("drop")
    p_drop.add_argument("id")
    sub.add_parser("apply")
    p_applied = sub.add_parser("applied", help="mark a resolved item as carried out by an agent session")
    p_applied.add_argument("id")
    p_applied.add_argument("--note", default="")
    sub.add_parser("html")
    p_exp = sub.add_parser("export", help="print a store with only one level's items")
    p_exp.add_argument("--level", choices=LEVELS, required=True)
    p_imp = sub.add_parser("import", help="merge a store file into this home's store")
    p_imp.add_argument("file")
    args = ap.parse_args()

    if args.cmd == "scan":
        added, dropped = scan(args.home)
        print(f"scan: {added} new, {dropped} dropped")
        print(render_text(load(args.home), scanned=scanned_at(args.home)))
    elif args.cmd == "list":
        print(render_text(load(args.home), args.all, scanned_at(args.home), args.level or ""))
    elif args.cmd == "add":
        with locked(args.home):
            data = load(args.home)
            item = new_item(data, "manual", args.title, detail=args.detail, options=args.options, source=args.source, level=args.level)
            save(data, args.home)
        print(f"added {item['id']}")
    elif args.cmd == "resolve":
        with locked(args.home):
            data = load(args.home)
            item = find(data, args.id)
            item.update(status="resolved", answer=args.answer, note=args.note, resolved=today())
            save(data, args.home)
        print(f"{item['id']} resolved: {args.answer}")
    elif args.cmd == "drop":
        with locked(args.home):
            data = load(args.home)
            find(data, args.id).update(status="dropped", resolved=today())
            save(data, args.home)
    elif args.cmd == "apply":
        print("\n".join(apply(args.home)) or "nothing to apply")
    elif args.cmd == "applied":
        with locked(args.home):
            data = load(args.home)
            item = find(data, args.id)
            item.update(applied=today(), note=args.note or item["note"])
            save(data, args.home)
    elif args.cmd == "html":
        print(render_html(load(args.home), scanned_at(args.home)), end="")
    elif args.cmd == "export":
        print(json.dumps(export_store(load(args.home), args.level), ensure_ascii=False, indent=1))
    elif args.cmd == "import":
        with open(args.file, encoding="utf-8") as fh:
            added, updated, unchanged = import_store(json.load(fh), args.home)
        print(f"import: {added} added, {updated} updated, {unchanged} unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
