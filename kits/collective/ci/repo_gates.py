"""Gates that only the collective repo needs. The shared ones (eol, size, paths, text, secrets, deny, ...) live
in ci/gates.py; this file registers the rest with `@gate(name, why)`. Why each exists: docs/ci-gates.md."""
from __future__ import annotations

import fnmatch
import os
import re
import sys
from pathlib import Path

from gates import Ctx, Finding, gate, scan

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lint_collective as lc  # noqa: E402

REDACTION = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")),
    ("ipv4", re.compile(r"\b(?!(?:127\.0\.0\.1|0\.0\.0\.0|192\.0\.2\.\d+|198\.51\.100\.\d+|203\.0\.113\.\d+)\b)"
                        r"(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b")),
    ("cpf", re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")),
    ("cnpj", re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")),
    ("phone-br", re.compile(r"(?<!\d)(?:\+55\s?)?\(?\d{2}\)?\s?9?\d{4}-\d{4}(?!\d)")),
    ("long-id", re.compile(r"\b[0-9a-fA-F]{32,}\b")),
]
LINT_GATE = {"invisible Unicode": "injection", "long base64 blob": "injection", "download-and-run": "injection",
             "instruction hidden from the user": "injection", ".denylist.local": "no-personal-data"}


def cfg(c: Ctx) -> dict:
    return c.cfg.get("collective", {})


@gate("registry", "an item with no owner, source and review date cannot be revalidated, so stale rules stay forever")
def g_registry(c: Ctx):
    for msg in lc.lint(str(c.root)):
        if not any(k in msg for k in LINT_GATE):
            path, _, rest = msg.partition(": ")
            yield Finding("registry", rest or msg, path if rest else "")


@gate("injection", "shared text is loaded by every agent: hidden Unicode, base64 or 'do not tell the user' is a supply-chain attack")
def g_injection(c: Ctx):
    for msg in lc.lint(str(c.root)):
        if any(msg.endswith(k) for k in ("invisible Unicode", "long base64 blob", "download-and-run",
                                        "instruction hidden from the user")):
            path, _, rest = msg.partition(": ")
            yield Finding("injection", rest, path)


@gate("redaction", "an e-mail, IP, CPF, CNPJ, phone or long id in shared text is personal or client data that left an ego")
def g_redaction(c: Ctx):
    yield from scan(c, "redaction", REDACTION, ["ci/*", "docs/ci-gates.md", ".github/*"])


def _terms(c: Ctx, env_var: str, local_name: str) -> list[str]:
    """Private term list: the repository variable (CI) plus a git-ignored file on a machine. Never committed."""
    terms = [t.strip().lower() for t in os.environ.get(env_var, "").split(",") if t.strip()]
    local = c.root / local_name
    if local.is_file():
        terms += [t.strip().lower() for t in local.read_text(encoding="utf-8").splitlines()
                  if t.strip() and not t.startswith("#")]
    return terms


def _scan_terms(c: Ctx, gate_name: str, terms: list[str]):
    for f in c.files:
        if c.match(["ci/*", "docs/ci-gates.md"], f):
            continue
        low = c.text(f).lower()
        for t in terms:
            if re.search(rf"(?<!\w){re.escape(t)}(?!\w)", low):
                yield Finding(gate_name, "contains a term from the private list (not printed)", f)


@gate("no-personal-data", "names of people and chats are not in a pattern list; they come from a private term list")
def g_no_personal(c: Ctx):
    k = cfg(c)
    var = k.get("env_terms_var", "COLLECTIVE_DENY_TERMS")
    terms = _terms(c, var, ".denylist.local")
    if not terms and c.strict and os.environ.get("CI"):
        yield Finding("no-personal-data", f"no private term list: set the repository variable {var} (comma separated)",
                      severity="warn")
    yield from _scan_terms(c, "no-personal-data", terms)


@gate("no-company-data", "this collective is shared across a company boundary: names of the other company and its clients must never appear")
def g_no_company(c: Ctx):
    k = cfg(c)
    var = k.get("env_companies_var", "COLLECTIVE_DENY_COMPANIES")
    terms = _terms(c, var, k.get("companies_local_file", ".denylist.companies.local"))
    if not terms and c.strict and os.environ.get("CI") and k.get("require_company_list_in_ci", True):
        yield Finding("no-company-data", f"no company term list: set the repository variable {var} (comma separated). "
                      "Without it this gate checks nothing")
    yield from _scan_terms(c, "no-company-data", terms)


@gate("generated-files", "a generated or machine-local file (AGENTS.md, caches, lint reports, .age) copied in will be loaded or leak")
def g_generated(c: Ctx):
    k = cfg(c)
    for f in c.files:
        p = Path(f)
        name = p.name
        if any(fnmatch.fnmatch(name, pat) for pat in k.get("forbidden_names", [])):
            yield Finding("generated-files", f"`{name}` is generated or machine-local; do not commit it", f)
        if any(part in k.get("forbidden_dirs", []) for part in p.parts[:-1]):
            yield Finding("generated-files", "folder is generated or belongs to another layer", f)
        if f.endswith((".md", ".json", ".py", ".sh")) and not c.match(["ci/*", "docs/ci-gates.md"], f):
            head = c.text(f)[:600]
            for m in k.get("generated_markers", []):
                if m in head:
                    yield Finding("generated-files", f"carries the generated-file marker `{m}`", f)


@gate("budget", "global/ and rules/ load into every session and share the Codex AGENTS.md limit (32 KiB) with all layers")
def g_budget(c: Ctx):
    k = cfg(c)
    limit = k.get("budget_bytes", 3600)
    total = 0
    for f in c.files:
        if Path(f).parts[0] in k.get("budget_dirs", ["global", "rules"]) and f.endswith(tuple(k.get("always_loaded_ext", [".md"]))):
            total += c.size(f)
    if total > limit:
        yield Finding("budget", f"always-loaded files are {total} bytes (> {limit}); move detail into a skill")


@gate("glossary-format", "the glossary is imported as-is by every harness; a broken table or a duplicated term makes it ambiguous")
def g_glossary(c: Ctx):
    k = cfg(c)
    rel = k.get("glossary")
    if not rel or rel not in c.files:
        yield Finding("glossary-format", f"{rel} is missing")
        return
    text = c.text(rel)
    lines = text.split("\n")
    if lines[0] != k.get("glossary_title"):
        yield Finding("glossary-format", f"first line must be `{k.get('glossary_title')}`", rel, 1)
    if text.startswith("---"):
        yield Finding("glossary-format", "no frontmatter: the file is imported into CLAUDE.md as text", rel, 1)
    if k.get("glossary_collision_header") not in lines:
        yield Finding("glossary-format", "missing the collisions table header", rel)
    if not text.endswith("\n"):
        yield Finding("glossary-format", "missing final newline", rel)
    seen: dict[str, int] = {}
    for i, ln in enumerate(lines, 1):
        if ln.startswith("#") and not re.match(r"^#{1,2} \S", ln):
            yield Finding("glossary-format", "only `#` and `##` headings, with a space", rel, i)
        if ln.startswith("- "):
            terms = re.findall(r"\*\*([^*]+)\*\*", ln)
            if not terms:
                yield Finding("glossary-format", "a list item must define at least one **term**", rel, i)
            for t in terms:
                key = t.lower()
                if key in seen:
                    yield Finding("glossary-format", f"term `{t}` already defined on line {seen[key]}", rel, i)
                seen.setdefault(key, i)
        elif ln.startswith("|") and ln.count("|") != 4 and not set(ln) <= set("|- "):
            yield Finding("glossary-format", "collisions table rows have exactly 3 columns", rel, i)
