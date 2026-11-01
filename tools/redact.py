"""Redaction for text that leaves the machine (used before any text is sent to an external gateway).

Narrow lexical patterns only (the team repo rule on redaction): secrets, personal identifiers and
addresses that can point at private systems. Each match becomes `<kind>`. The PASS/BLOCK corpus
lives in tests/test_tools.py.
"""
import re

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("api_key", re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}")),
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("url", re.compile(r"\bhttps?://[^\s)>\]\"']+")),
    ("ip", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("cpf", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")),
    ("cnpj", re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")),
    ("phone", re.compile(r"(?<!\w)\+?\(?\d{2,3}\)?[\s-]?9?\d{4}[\s-]?\d{4}\b")),
    ("long_id", re.compile(r"\b[0-9a-f]{24,}\b|\b\d{12,}\b")),
]
# A value after one of these words becomes `<secret>` (placeholders like $VAR or <x> are kept).
# Needs ":" or "=" (or "Bearer <value>"), so prose like "secret management" is kept.
SECRET_KEYS = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|senha|password|passwd|pwd)\b[\"']?\s*[:=]\s*\S+|\b(bearer)\s+\S+")


def _redact_secret_assignments(text: str) -> str:
    def fix(m: re.Match[str]) -> str:
        key = m.group(1) or m.group(2)
        value = m.group(0)[len(key):].lstrip(" :=")
        if value.startswith(("$", "<", "{")) or len(value.strip("\"'")) < 6:
            return m.group(0)
        return f"{key}=<secret>"

    return SECRET_KEYS.sub(fix, text)


def redact(text: str) -> str:
    text = _redact_secret_assignments(text)
    for kind, rx in PATTERNS:
        if kind == "url":
            text = rx.sub(lambda m: "<url:" + m.group(0).split("/")[2] + ">", text)
        else:
            text = rx.sub(f"<{kind}>", text)
    return text
