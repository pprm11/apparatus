#!/usr/bin/env python3
"""Write-time secret check for memory files (no model, no network). Never prints a secret value.

  python -I tools/secret_gate.py FILE [FILE ...]   # exit 1 and `file:line kind` for each hit; exit 0 if clean

A hit is a line the redaction patterns (tools/redact.py) would rewrite as a secret: private keys, JWTs, provider
tokens, or a `key=value` assignment whose key says secret/token/password and whose value is not a placeholder
(`$VAR`, `<x>`, `{x}`, under 6 characters). Personal data (email, url, ip) is not a secret here: the egress
filter handles it. The output carries the file, the line number and the kind only.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops the script dir from sys.path
import redact  # noqa: E402

SECRET_KINDS = ("private_key", "jwt", "github_token", "api_key", "aws_key")


def find_secrets(text: str) -> list[tuple[int, str]]:
    """(line number, kind) for every line that holds a secret; the value is never returned."""
    hits: list[tuple[int, str]] = []
    for kind, rx in redact.PATTERNS:
        if kind not in SECRET_KINDS:
            continue
        for m in rx.finditer(text):
            hits.append((text.count("\n", 0, m.start()) + 1, kind))
    for no, line in enumerate(text.splitlines(), 1):
        if redact._redact_secret_assignments(line) != line:
            hits.append((no, "assignment"))
    return sorted(set(hits))


def scan_file(path: str) -> list[tuple[int, str]]:
    try:
        with open(path, encoding="utf-8") as fh:
            return find_secrets(fh.read().replace("\r\n", "\n"))
    except OSError:
        return []


def main(argv: list[str]) -> int:
    bad = 0
    for path in argv:
        for no, kind in scan_file(path):
            print(f"{path}:{no} {kind}")
            bad += 1
    if bad:
        print(f"{bad} secret-like line(s); keep the value out of memory (use an environment variable name) and rotate it if real.",
              file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
