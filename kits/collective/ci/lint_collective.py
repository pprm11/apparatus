#!/usr/bin/env python3
"""Gate for the collective layer: every shared item is registered with provenance and nothing carries
hidden instructions or a listed private term.

  python -I ci/lint_collective.py [--root .]

Checks (exit 1 on any finding):
  1. registry.json lists every file under global/ and rules/, and every skill folder under skills/.
  2. Each entry has owner, source, created, review_by, status (draft|stable|deprecated), locked (bool).
     A deprecated entry needs superseded_by. review_by must be an ISO date.
  3. Skill folders are named collective-<name>, and SKILL.md has `name:` equal to the folder and `level: collective`.
  4. Text files hold no invisible Unicode, no long base64 blob, no download-and-run line and none of the
     phrases that hide instructions from the user.
  5. If .denylist.local exists (one term per line, never committed), no file contains a listed term.
"""
import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

STATUS = {"draft", "stable", "deprecated"}
REQUIRED = ("owner", "source", "created", "review_by", "status", "locked")
INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤﻿]")
BASE64 = re.compile(r"[A-Za-z0-9+/]{120,}={0,2}")
RUN = re.compile(r"(curl|wget)[^\n|]*\|\s*(ba)?sh|Invoke-Expression|iex\s*\(", re.I)
HIDE = re.compile(r"(do not|don't|never)\s+(tell|inform|mention to)\s+the\s+user|ignore (all )?(previous|prior) instructions", re.I)
MANAGED = ("global", "rules", "skills")
SKIP_NAMES = {".gitkeep"}


def managed_files(root: str) -> list[str]:
    out = []
    for top in MANAGED:
        for base, _dirs, files in os.walk(os.path.join(root, top)):
            for f in files:
                if f not in SKIP_NAMES:
                    out.append(os.path.relpath(os.path.join(base, f), root).replace(os.sep, "/"))
    return sorted(out)


def lint(root: str) -> list[str]:
    errs: list[str] = []
    reg_path = os.path.join(root, "registry.json")
    reg = json.loads(Path(reg_path).read_text(encoding="utf-8")) if os.path.isfile(reg_path) else {}
    entries = reg.get("items", {})
    files = managed_files(root)
    for f in files:
        if not f.startswith("skills/") and f not in entries:
            errs.append(f"{f}: not in registry.json")
    skill_dirs = sorted({f.split("/")[1] for f in files if f.startswith("skills/") and f.count("/") >= 2})
    for d in skill_dirs:
        key = f"skills/{d}"
        if key not in entries:
            errs.append(f"{key}: not in registry.json")
        if not d.startswith("collective-"):
            errs.append(f"{key}: skill folder must start with collective-")
        sk = os.path.join(root, "skills", d, "SKILL.md")
        if not os.path.isfile(sk):
            errs.append(f"{key}: SKILL.md missing")
            continue
        head = Path(sk).read_text(encoding="utf-8")[:4096]
        if not re.search(rf"^name:\s*{re.escape(d)}\s*$", head, re.M):
            errs.append(f"{key}: frontmatter name must equal the folder name")
        if not re.search(r"^level:\s*collective\s*$", head, re.M):
            errs.append(f"{key}: frontmatter needs level: collective")
    for key, e in entries.items():
        if key not in files and not any(f.startswith(key + "/") for f in files):
            errs.append(f"{key}: in registry.json but missing on disk")
        for field in REQUIRED:
            if field not in e:
                errs.append(f"{key}: registry field {field} missing")
        if e.get("status") not in STATUS:
            errs.append(f"{key}: status must be one of {sorted(STATUS)}")
        if e.get("status") == "deprecated" and not e.get("superseded_by"):
            errs.append(f"{key}: deprecated needs superseded_by")
        try:
            datetime.date.fromisoformat(str(e.get("review_by")))
        except ValueError:
            errs.append(f"{key}: review_by must be an ISO date")
        if not isinstance(e.get("locked"), bool):
            errs.append(f"{key}: locked must be true or false")
    deny = []
    dl = os.path.join(root, ".denylist.local")
    if os.path.isfile(dl):
        deny = [t.strip().lower() for t in Path(dl).read_text(encoding="utf-8").splitlines() if t.strip() and not t.startswith("#")]
    for f in files:
        try:
            text = Path(root, f).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errs.append(f"{f}: not UTF-8 text")
            continue
        for name, rx in (("invisible Unicode", INVISIBLE), ("long base64 blob", BASE64),
                         ("download-and-run", RUN), ("instruction hidden from the user", HIDE)):
            if rx.search(text):
                errs.append(f"{f}: {name}")
        low = text.lower()
        for term in deny:
            if term in low:
                errs.append(f"{f}: contains a term from .denylist.local")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    errs = lint(os.path.abspath(args.root))
    for e in errs:
        print(e)
    print(f"{len(errs)} finding(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
