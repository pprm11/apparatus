#!/usr/bin/env python3
"""Deterministic health check for the memory/ folder of this repo (no model, no network).

Usage: python -I tools/lint_memory.py [memory_dir] [--schema-root DIR] [--sibling DIR ...]
    -> markdown report on stdout, exit 0.
(--schema-root: where the always-loaded schema files live, `global/` + `rules/` as in this repo or the
~/.claude layout; default is the parent of memory_dir. --sibling: memory folders of the other layer
repos of the same ~/.claude; a link, an index line or a MEMORY.md that lives in a sibling is not a
problem, since the layers only split one memory tree by level.)

Checks: frontmatter fields, name vs filename, broken [[links]], index drift (files missing from
MEMORY.md and index lines pointing to missing files), index size against the 200-line / 25KB load
limit, same name in more than one project (candidate for ~/.claude/rules/), and project memories
not modified for STALE_DAYS (candidate for review). Warnings, in a separate section that does not
count as problems: keywords outside 6-15, no `modified` date, body over 3 KB, absolute size claims
("N KB de 32 KB") that go stale, memories that mostly repeat a schema file, an unknown `metadata.kind` or a non-ISO `metadata.review_by`,
and secret-like lines (file, line and kind only). The report has no
timestamps or day counts on purpose, so it only changes when the findings change.
"""
import argparse
import os
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops the script dir from sys.path
import layers  # noqa: E402
import secret_gate  # noqa: E402

STALE_DAYS = 21
INDEX_WARN_LINES = 150
INDEX_WARN_BYTES = 20_000
KEYWORDS_MIN, KEYWORDS_MAX = 6, 15
KINDS = ("decision", "project", "preference", "machine", "reference")  # memlife fact kinds (release 1: warning only)
BODY_WARN_BYTES = 3 * 1024
SHINGLE = 8  # words
DUPLICATE_RATIO = 0.30
MIN_SHINGLES = 5  # below this a memory is too short to call a duplicate
SCHEMA_FILES = ("CLAUDE.md", "regras-de-agente.md")
SIZE_CLAIM = re.compile(
    r"(?i)(?<![\d.,])\d[\d.,]*\s*(?:KiB|KB|bytes?|B)\b\s*(?:de|of|/)\s*\d[\d.,]*\s*(?:KiB|KB|bytes?|B)\b")

FRONT = re.compile(r"^---\n(.*?)\n---\n", re.S)
LINK = re.compile(r"\[\[([^\]]+)\]\]")
INDEX_REF = re.compile(r"\]\(([^)]+\.md)\)")


def field(front: str, key: str) -> str:
    m = re.search(rf"^\s*{key}:\s*(.+)$", front, re.M)
    return m.group(1).strip() if m else ""


def load(root: str) -> dict[str, dict[str, dict[str, str]]]:
    projects: dict[str, dict[str, dict[str, str]]] = {}
    for proj in sorted(os.listdir(root)):
        pdir = os.path.join(root, proj)
        if not os.path.isdir(pdir):
            continue
        files = {}
        for name in sorted(os.listdir(pdir)):
            if not name.endswith(".md"):
                continue
            path = os.path.join(pdir, name)
            with open(path, encoding="utf-8") as fh:
                text = fh.read().replace("\r\n", "\n")
            files[name] = {"text": text, "mtime": str(os.path.getmtime(path))}
        projects[proj] = files
    return projects


def sealed_memories(sealed_root: str) -> dict[str, dict[str, dict[str, str]]]:
    """proj -> {name.md: empty info} for memories a layer keeps only as sealed/projects/<proj>/memory/<name>.md.age."""
    out: dict[str, dict[str, dict[str, str]]] = {}
    base = os.path.join(sealed_root, "projects")
    if not os.path.isdir(base):
        return out
    for proj in sorted(os.listdir(base)):
        mem = os.path.join(base, proj, "memory")
        if os.path.isdir(mem):
            for name in sorted(os.listdir(mem)):
                if name.endswith(".md.age"):
                    out.setdefault(proj, {})[name[:-4]] = {"text": "", "mtime": "", "sealed": "1"}
    return out


def check_project(proj: str, files: dict[str, dict[str, str]], all_names: set[str], out: list[str],
                  sibling: dict[str, dict[str, str]] | None = None) -> None:
    """`sibling`: the same project's files in the other layers (name -> info), merged; may be empty."""
    sibling = sibling or {}
    index = files.get("MEMORY.md", {}).get("text", "") or sibling.get("MEMORY.md", {}).get("text", "")
    if not index:
        out.append(f"- `{proj}`: MEMORY.md missing")
    lines = [ln for ln in index.splitlines() if ln.strip()]
    if len(lines) > INDEX_WARN_LINES or len(index.encode()) > INDEX_WARN_BYTES:
        out.append(f"- `{proj}`: MEMORY.md has {len(lines)} lines / {len(index.encode())} bytes (load limit 200 / 25KB)")
    if "MEMORY.md" in files:  # the layer that holds the index answers for its lines
        for ref in sorted(set(INDEX_REF.findall(index))):
            if ref not in files and ref not in sibling:
                out.append(f"- `{proj}`: index points to missing file `{ref}`")
    for name, info in files.items():
        if name == "MEMORY.md":
            continue
        text = info["text"]
        m = FRONT.match(text)
        if not m:
            out.append(f"- `{proj}/{name}`: no frontmatter")
            continue
        front = m.group(1)
        for key in ("name", "description", "type"):
            if not field(front, key):
                out.append(f"- `{proj}/{name}`: frontmatter missing `{key}`")
        if f"({name})" not in index:
            out.append(f"- `{proj}/{name}`: not listed in MEMORY.md")
        for target in sorted({t.split("|")[0].strip() for t in LINK.findall(text)}):
            if "/" not in target and target not in all_names:  # path links resolved by graph_view --check
                out.append(f"- `{proj}/{name}`: link [[{target}]] has no memory with that name (ok if it marks a memory to write)")


def stale(projects: dict[str, dict[str, dict[str, str]]]) -> list[str]:
    out = []
    now = time.time()
    for proj, files in projects.items():
        for name, info in files.items():
            m = FRONT.match(info["text"])
            if name == "MEMORY.md" or not m or field(m.group(1), "type") != "project":
                continue
            modified = field(m.group(1), "modified")
            try:
                ts = datetime.fromisoformat(modified.strip("'\"").replace("Z", "+00:00")).timestamp()
            except ValueError:
                ts = float(info["mtime"])
            age = (now - ts) / 86400
            if age > STALE_DAYS:
                out.append(f"- `{proj}/{name}`: project memory untouched for more than {STALE_DAYS} days")
    return out


def shingles(text: str) -> set[tuple[str, ...]]:
    w = re.findall(r"\w+", text.lower())
    return {tuple(w[i:i + SHINGLE]) for i in range(len(w) - SHINGLE + 1)}


def schema_texts(root: str) -> dict[str, str]:
    """name -> text of the always-loaded schema files under `root` (repo layout or ~/.claude layout)."""
    base = os.path.join(root, "global") if os.path.isdir(os.path.join(root, "global")) else root
    paths = [os.path.join(base, n) for n in SCHEMA_FILES]
    rules = os.path.join(root, "rules")
    if os.path.isdir(rules):
        paths += [os.path.join(rules, n) for n in sorted(os.listdir(rules)) if n.endswith(".md")]
    out = {}
    for path in paths:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                out[os.path.relpath(path, root).replace(os.sep, "/")] = fh.read().replace("\r\n", "\n")
    return out


def warnings(projects: dict[str, dict[str, dict[str, str]]], schema: dict[str, str]) -> list[str]:
    out = []
    schema_sh = {name: shingles(text) for name, text in schema.items()}
    for proj, files in projects.items():
        for name, info in files.items():
            m = FRONT.match(info["text"])
            if name == "MEMORY.md" or not m:
                continue
            front, body = m.group(1), info["text"][m.end():]
            who = f"`{proj}/{name}`"
            count = len([k for k in field(front, "keywords").split(",") if k.strip()])
            if not KEYWORDS_MIN <= count <= KEYWORDS_MAX:
                out.append(f"- {who}: {count} keywords (expected {KEYWORDS_MIN}-{KEYWORDS_MAX})")
            if not field(front, "modified"):
                out.append(f"- {who}: no `metadata.modified` (decay falls back to the file mtime, which the sync resets)")
            kind = field(front, "kind")
            if kind and kind not in KINDS:
                out.append(f"- {who}: `metadata.kind` is '{kind}' (expected one of {', '.join(KINDS)})")
            review_by = field(front, "review_by").strip("'\"")
            if review_by:
                try:
                    datetime.fromisoformat(review_by)
                except ValueError:
                    out.append(f"- {who}: `metadata.review_by` '{review_by}' is not an ISO date")
            for no, skind in secret_gate.find_secrets(info["text"]):  # file, line and kind only; never the value
                out.append(f"- {who}: line {no} looks like a secret ({skind}); keep the value out of memory and rotate it if real")
            if len(body.encode()) > BODY_WARN_BYTES:
                out.append(f"- {who}: body is {len(body.encode()) / 1024:.1f} KB (over {BODY_WARN_BYTES // 1024} KB; split or trim)")
            for claim in SIZE_CLAIM.finditer(body):
                out.append(f"- {who}: absolute size claim '{claim.group(0)}' goes stale; link the file or drop the number")
            mine = shingles(body)
            if len(mine) >= MIN_SHINGLES:
                for sname, theirs in schema_sh.items():
                    ratio = len(mine & theirs) / len(mine)
                    if ratio > DUPLICATE_RATIO:
                        out.append(f"- {who}: {int(ratio * 100)}% of its {SHINGLE}-word runs also appear in `{sname}` (near-duplicate)")
    return out


def long_key_warnings(root: str) -> list[str]:
    """Memory folders whose project key is over the layers.py limit (the original key is read from the
    `.project-key` marker of a shortened folder), so the report shows which scratch sessions leave memories."""
    out = []
    for folder in sorted(os.listdir(root)):
        marker = os.path.join(root, folder, layers.PROJECT_KEY_MARKER)
        key = folder
        if os.path.isfile(marker):
            with open(marker, encoding="utf-8") as fh:
                key = fh.read().strip() or folder
        if len(key) > layers.PROJECT_KEY_LIMIT:
            out.append(f"- `{folder}`: project key of {len(key)} characters (over {layers.PROJECT_KEY_LIMIT}; "
                       "a session without a folder?), exported under a shortened name")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("memory_dir", nargs="?", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "memory"))
    ap.add_argument("--schema-root")
    ap.add_argument("--sibling", action="append", default=[], help="memory folder of another layer repo")
    args = ap.parse_args()
    root = args.memory_dir
    projects = load(root)
    siblings: dict[str, dict[str, dict[str, str]]] = {}
    for sdir in args.sibling:
        if os.path.isdir(sdir) and os.path.abspath(sdir) != os.path.abspath(root):
            for proj, files in load(sdir).items():
                siblings.setdefault(proj, {}).update(files)
    for sdir in [root] + list(args.sibling):  # memories kept only encrypted (sealed/projects/K/memory/F.md.age)
        for proj, files in sealed_memories(os.path.join(os.path.dirname(os.path.abspath(sdir)), "sealed")).items():
            siblings.setdefault(proj, {}).update(files)
    schema = schema_texts(args.schema_root or os.path.dirname(os.path.abspath(root)))
    names: dict[str, list[str]] = {}
    for proj, files in projects.items():
        for name, info in files.items():
            m = FRONT.match(info["text"])
            if m and field(m.group(1), "name"):
                names.setdefault(field(m.group(1), "name"), []).append(proj)
    known = set(names)
    for files in siblings.values():  # names in the other layers resolve [[links]] too, but do not count as shared
        for name, info in files.items():
            m = FRONT.match(info["text"])
            if m and field(m.group(1), "name"):
                known.add(field(m.group(1), "name"))
            elif info.get("sealed"):
                known.add(name[:-3])  # a sealed memory is named after its file
    problems: list[str] = []
    for proj, files in projects.items():
        check_project(proj, files, known, problems, siblings.get(proj))
    shared = [f"- `{n}` in {', '.join(p)}" for n, p in sorted(names.items()) if len(set(p)) > 1]
    total = sum(len(f) - ("MEMORY.md" in f) for f in projects.values())

    print("# Memory lint report\n")
    print(f"{total} memories in {len(projects)} projects. {len(problems)} problems.\n")
    print("## Problems\n")
    print("\n".join(problems) or "None.")
    print("\n## Same name in more than one project (candidate for ~/.claude/rules/)\n")
    print("\n".join(shared) or "None.")
    print(f"\n## Project memories older than {STALE_DAYS} days (review)\n")
    print("\n".join(stale(projects)) or "None.")
    warned = warnings(projects, schema) + long_key_warnings(root)
    print(f"\n## Warnings ({len(warned)}; not counted as problems)\n")
    print("\n".join(warned) or "None.")


if __name__ == "__main__":
    main()
