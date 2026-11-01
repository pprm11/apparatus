#!/usr/bin/env python3
"""Validate what the harvest model wrote before it is copied into ~/.claude/projects/<proj>/memory/.

Usage: python -I tools/validate_harvest.py OUT_MEMORY_DIR PROJECTS_DIR
  OUT_MEMORY_DIR  <session>/out/memory, with <project>/<slug>.md files and optional <project>/MEMORY.add
  PROJECTS_DIR    ~/.claude/projects

Prints one tab-separated line per decision:
  OK<TAB><project>/<file>.md
  ADD<TAB><project><TAB><index line>
  REJECT<TAB><project>/<file><TAB><reason>
Rules: frontmatter with name, description and metadata.type; name equals the file name; under 8 KB; at most
3 files; the project's memory folder already exists; never overwrite a file of type user or feedback or one
marked pinned: true; no MEMORY.md.
"""
import os
import re
import sys

MAX_BYTES = 8 * 1024
MAX_FILES = 3
PROTECTED_TYPES = {"user", "feedback"}


def frontmatter(text: str):
    """Returns (name, description, type, pinned) or None when there is no frontmatter."""
    text = text.lstrip("﻿")
    m = re.match(r"---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return None
    block = m.group(1)
    name = re.search(r"^name:\s*(.+?)\s*$", block, re.M)
    desc = re.search(r"^description:\s*(.+?)\s*$", block, re.M)
    meta = re.search(r"^metadata:\s*\r?\n((?:[ \t]+.*\r?\n?)+)", block + "\n", re.M)
    mtype = re.search(r"^[ \t]+type:\s*(\S+)", meta.group(1), re.M) if meta else None
    pinned = re.search(r"^[ \t]*pinned:\s*true\b", block, re.M | re.I)

    def unq(s: str) -> str:
        return s.strip().strip("\"'")

    return (
        unq(name.group(1)) if name else "",
        unq(desc.group(1)) if desc else "",
        unq(mtype.group(1)) if mtype else "",
        bool(pinned),
    )


def read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def validate(out_dir: str, projects_dir: str) -> list:
    lines = []
    accepted = {}  # project -> set of slugs
    count = 0
    seen_names: list = []
    projects = sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else []
    for proj in projects:
        pdir = os.path.join(out_dir, proj)
        if not os.path.isdir(pdir):
            continue
        target_dir = os.path.join(projects_dir, proj, "memory")
        safe_proj = bool(re.fullmatch(r"[A-Za-z0-9._-]+", proj)) and ".." not in proj
        for fname in sorted(os.listdir(pdir)):
            if not fname.endswith(".md"):
                continue
            rel = f"{proj}/{fname}"
            path = os.path.join(pdir, fname)

            def reject(reason: str, rel: str = rel) -> None:
                lines.append(f"REJECT\t{rel}\t{reason}")

            if not safe_proj:
                reject("unsafe project name")
            elif not os.path.isdir(target_dir):
                reject("project memory folder does not exist")
            elif fname.casefold() == "memory.md":
                reject("index files are not accepted (use MEMORY.add)")
            elif not re.fullmatch(r"[A-Za-z0-9._-]+\.md", fname):
                reject("unsafe file name")
            elif os.path.getsize(path) >= MAX_BYTES:
                reject("file is 8 KB or more")
            elif count >= MAX_FILES:
                reject("more than 3 files in one run")
            else:
                fm = frontmatter(read(path))
                if fm is None:
                    reject("no frontmatter")
                    continue
                name, desc, mtype, _ = fm
                if not name or not desc or not mtype:
                    reject("frontmatter needs name, description and metadata.type")
                    continue
                if name != fname[:-3]:
                    reject(f"name '{name}' differs from the file name")
                    continue
                # Windows paths are case-insensitive: memory.md would overwrite MEMORY.md.
                clash = [n for n in os.listdir(target_dir) if n.casefold() == fname.casefold()]
                if clash and clash[0] != fname:
                    reject(f"name differs only in case from existing {clash[0]}")
                    continue
                if any(f.casefold() == rel.casefold() for f in seen_names):
                    reject("duplicate name in this run (case-insensitive)")
                    continue
                seen_names.append(rel)
                existing = os.path.join(target_dir, fname)
                if os.path.isfile(existing):
                    old = frontmatter(read(existing))
                    if old and (old[2] in PROTECTED_TYPES or old[3]):
                        reject("existing memory is type user/feedback or pinned")
                        continue
                count += 1
                accepted.setdefault(proj, set()).add(fname[:-3])
                lines.append(f"OK\t{rel}")
    # Index lines: only for accepted files, and only if the project index does not link them yet.
    for proj, slugs in accepted.items():
        add = os.path.join(out_dir, proj, "MEMORY.add")
        if not os.path.isfile(add):
            continue
        idx_path = os.path.join(projects_dir, proj, "memory", "MEMORY.md")
        idx = read(idx_path) if os.path.isfile(idx_path) else ""
        for entry in read(add).splitlines():
            entry = entry.strip()
            if not entry:
                continue
            m = re.match(r"- \[[^\]]+\]\(([A-Za-z0-9._-]+)\.md\)", entry)
            if not m or len(entry) > 300 or m.group(1) not in slugs:
                lines.append(f"REJECT\t{proj}/MEMORY.add\tbad index line")
            elif f"]({m.group(1)}.md)" not in idx:
                lines.append(f"ADD\t{proj}\t{entry}")
    return lines


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # LF only: the shell reads names line by line
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    for line in validate(sys.argv[1], sys.argv[2]):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
