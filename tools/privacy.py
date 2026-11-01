#!/usr/bin/env python3
"""Privacy gate for a person install: find owner, company, client and colleague names in text that is about to
reach another person's machine (or already did).

  python -I tools/privacy.py scan PATH... [--allow-word WORD ...] [--json]     exit 1 when anything matches

The patterns live in ci/privacy-terms.json (one source for CI, the tests and `onboard.py init`). `--allow-word`
drops every pattern that matches the word, which is how a person whose own name is on the list can still scan.
Binary and very large files are skipped; file and folder names are scanned too.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

TERMS = Path(__file__).resolve().parent.parent / "ci" / "privacy-terms.json"
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}
MAX_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class Hit:
    path: str
    line: int          # 0 = the file name itself
    rule: str
    text: str = ""

    def __str__(self) -> str:
        where = self.path if not self.line else f"{self.path}:{self.line}"
        return f"{where}: {self.rule}" + (f": {self.text}" if self.text else "")


def load_config(path: Path | None = None) -> dict:
    return json.loads((path or TERMS).read_text(encoding="utf-8"))


def patterns(cfg: dict | None = None, allow_words: Iterable[str] = ()) -> list[tuple[str, re.Pattern]]:
    cfg = cfg or load_config()
    words = [w for w in (x.strip() for x in allow_words) if w]
    out = []
    for p in cfg["patterns"]:
        rx = re.compile(p["regex"], re.I)
        if not any(rx.search(w) for w in words):
            out.append((p["name"], rx))
    return out


def name_words(*texts: str) -> list[str]:
    """Words of a person's name, e-mail and account that may legitimately appear in their own files."""
    return [w for t in texts for w in re.split(r"[^\w]+", t) if len(w) >= 3]


def forbidden_layer(url: str, cfg: dict | None = None) -> str | None:
    """The forbidden-repo pattern that `url` matches, or None."""
    cfg = cfg or load_config()
    flat = url.strip().replace(chr(92), "/")
    for rx in cfg["forbidden_layer_repos"]:
        if re.search(rx, flat, re.I):
            return rx
    return None


def scan_text(text: str, pats: Sequence[tuple[str, re.Pattern]], label: str) -> list[Hit]:
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        for name, rx in pats:
            if rx.search(line):
                hits.append(Hit(label, n, name, line.strip()[:80]))
    return hits


def iter_files(root: Path) -> Iterable[Path]:
    if root.is_file():
        yield root
        return
    for p in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        if p.is_file():
            yield p


def scan_paths(paths: Iterable[Path], pats: Sequence[tuple[str, re.Pattern]], base: Path | None = None) -> list[Hit]:
    hits: list[Hit] = []
    for root in paths:
        for f in iter_files(Path(root)):
            label = (f.relative_to(base) if base and f.is_relative_to(base) else f).as_posix()
            hits += [Hit(label, 0, name) for name, rx in pats if rx.search(f.name)]
            try:
                if f.stat().st_size > MAX_BYTES:
                    continue
                text = f.read_bytes().decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            hits += scan_text(text, pats, label)
    return hits


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["scan"])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--allow-word", action="append", default=[])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    hits = scan_paths([Path(p) for p in args.paths], patterns(allow_words=args.allow_word))
    if args.json:
        print(json.dumps([vars(h) for h in hits], indent=1))
    else:
        for h in hits:
            print(h)
        print(f"{len(hits)} hit(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
