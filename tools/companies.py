#!/usr/bin/env python3
"""Map a folder to the company that owns it, from a companies.json kept outside every layer repo.

companies.json (default ~/.claude/companies.json, override with $COMPANIES_FILE or an argument):

  {"companies": {"<name>": {"ego": "<repo dir>", "collective": "<repo dir>",
                            "prefixes": ["~/Codes/app-*", "~/Codes/shared"],
                            "home": {"claude": "~/.agent-homes/<name>/claude", "codex": "~/.agent-homes/<name>/codex"}}},
   "default": null}

Rules for `prefixes`: forward slashes on every OS, `~` is the user home, `*` matches inside one path segment,
`**` crosses segments, and a pattern that matches a folder also covers everything below it. The first company
(in file order), then the first prefix (in list order), that matches wins. No match is None: such a folder
loads no company layer (ego, collective). Paths are compared as text; nothing is resolved on disk, so a
folder that does not exist yet maps like one that does. Case is ignored on Windows and macOS.

  python -I tools/companies.py of <path> [--companies FILE]          # prints the company name, or nothing
  python -I tools/companies.py home <company> <claude|codex> [--companies FILE]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HARNESSES = ("claude", "codex")
CASE_INSENSITIVE = sys.platform in ("win32", "darwin")


def default_file() -> Path:
    return Path(os.environ.get("COMPANIES_FILE") or "~/.claude/companies.json").expanduser()


def load(path: str | os.PathLike | None = None) -> dict:
    """Parsed companies.json. A missing file is an error: mapping nothing silently would hide the problem."""
    p = Path(path).expanduser() if path else default_file()
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data.get("companies"), dict):
        raise ValueError(f"{p}: missing the `companies` object")
    return data


def norm(path: str | os.PathLike) -> str:
    """Absolute path as text: `~` expanded, forward slashes, no trailing slash, case folded where the OS does."""
    text = os.path.abspath(os.path.expanduser(os.fspath(path))).replace("\\", "/")
    text = text.rstrip("/") or "/"
    return text.lower() if CASE_INSENSITIVE else text


def _pattern(prefix: str) -> re.Pattern:
    text = norm(prefix) if not prefix.startswith("*") else prefix.replace("\\", "/")
    out, i = [], 0
    while i < len(text):
        if text.startswith("**", i):
            out.append(".*")
            i += 2
        elif text[i] == "*":
            out.append("[^/]*")
            i += 1
        elif text[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(text[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def _ancestors(text: str):
    """text, then each parent, up to the root."""
    while True:
        yield text
        parent = text.rsplit("/", 1)[0]
        if not parent or parent == text or text.endswith(":"):
            return
        text = parent


def company_of(path: str | os.PathLike, data: dict | None = None) -> str | None:
    """Company that owns `path` (first matching prefix), or None."""
    data = data if data is not None else load()
    chain = list(_ancestors(norm(path)))
    for name, cfg in data["companies"].items():
        for prefix in cfg.get("prefixes", []):
            rx = _pattern(prefix)
            if any(rx.match(p) for p in chain):
                return name
    return None


def companies_of(path: str | os.PathLike, data: dict | None = None) -> list[str]:
    """Every company whose prefixes match `path`; more than one means the mapping is ambiguous."""
    data = data if data is not None else load()
    chain = list(_ancestors(norm(path)))
    return [name for name, cfg in data["companies"].items()
            if any(_pattern(p).match(c) for p in cfg.get("prefixes", []) for c in chain)]


def home_of(company: str, harness: str, data: dict | None = None) -> Path | None:
    """Agent home (CLAUDE_CONFIG_DIR or CODEX_HOME) of a company, with `~` expanded, or None when not declared."""
    if harness not in HARNESSES:
        raise ValueError(f"harness must be one of {HARNESSES}, got {harness!r}")
    data = data if data is not None else load()
    raw = data["companies"].get(company, {}).get("home", {}).get(harness)
    return Path(raw).expanduser() if raw else None


def owner_of(path: str | os.PathLike, data: dict | None = None) -> str | None:
    """Like company_of, but a folder inside a company's agent home also belongs to that company."""
    data = data if data is not None else load()
    found = company_of(path, data)
    if found:
        return found
    chain = list(_ancestors(norm(path)))
    for name, cfg in data["companies"].items():
        for raw in cfg.get("home", {}).values():
            if norm(raw) in chain:
                return name
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--companies", help="companies.json (default ~/.claude/companies.json or $COMPANIES_FILE)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_of = sub.add_parser("of")
    p_of.add_argument("path")
    p_home = sub.add_parser("home")
    p_home.add_argument("company")
    p_home.add_argument("harness", choices=HARNESSES)
    args = ap.parse_args()
    data = load(args.companies)
    if args.cmd == "of":
        found = company_of(args.path, data)
        if found:
            print(found)
        return 0 if found else 1
    home = home_of(args.company, args.harness, data)
    if home:
        print(home)
    return 0 if home else 1


if __name__ == "__main__":
    sys.exit(main())
