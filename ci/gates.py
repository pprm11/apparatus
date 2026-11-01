#!/usr/bin/env python3
"""Shared CI gate runner for the agent-context repos (superego, psique, ego-*, id-context).

Stdlib only. The same entry point runs in GitHub Actions, in pre-commit and by hand:

    python -I ci/gates.py                  # every gate that applies
    python -I ci/gates.py --list           # gates and the one-line reason for each
    python -I ci/gates.py --only eol,size  # a subset
    python -I ci/gates.py --staged         # only staged files (pre-commit)
    python -I ci/gates.py --strict         # a missing external tool (shellcheck, ruff...) is an error

Per-repo settings live in ci/config.json; per-repo gates live in ci/repo_gates.py and register with
`@gate(name, why)`. Every gate yields findings; any error finding makes the run fail (exit 1).
Why each gate exists: docs/ci-gates.md.
"""
from __future__ import annotations

import argparse
import atexit
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "ci" / "config.json"
FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
WIKILINK = re.compile(r"\[\[([^\]\|#]+)(?:[#|][^\]]*)?\]\]")
MDLINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
CONVENTIONAL = re.compile(r"(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9._/-]+\))?!?: \S.*")
MAX_TITLE = 100


def title_ok(title: str) -> bool:
    """Whole-title match on the stripped title, at most MAX_TITLE characters in total."""
    t = title.strip()
    return bool(CONVENTIONAL.fullmatch(t)) and len(t) <= MAX_TITLE
WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


@dataclass
class Finding:
    gate: str
    msg: str
    path: str = ""
    line: int = 0
    severity: str = "error"  # error | warn


GATES: dict[str, tuple[Callable[["Ctx"], Iterable[Finding]], str]] = {}


def gate(name: str, why: str):
    def deco(fn):
        GATES[name] = (fn, why)
        return fn
    return deco


class GitError(RuntimeError):
    """A git command failed. A gate must never read that as an empty answer."""


class Ctx:
    def __init__(self, root: Path, cfg: dict, staged: bool, strict: bool, title: str | None):
        self.root, self.cfg, self.staged, self.strict, self.title = root, cfg, staged, strict, title
        self._files: list[str] | None = None
        self._tool_root: Path | None = None

    def _git_bytes(self, args) -> bytes:
        try:
            r = subprocess.run(["git", *args], cwd=self.root, capture_output=True, check=False)
        except OSError as e:
            raise GitError(f"git {' '.join(args[:2])}: {e}") from e
        if r.returncode != 0:
            err = r.stderr.decode("utf-8", "replace").strip().splitlines()
            raise GitError(f"git {' '.join(args[:2])} exited {r.returncode}: {err[-1] if err else 'no output'}")
        return r.stdout

    def git(self, *args: str) -> str:
        return self._git_bytes(args).decode("utf-8", "replace")

    @property
    def files(self) -> list[str]:
        """Tracked files (index), or staged additions/changes with --staged. Posix paths."""
        if self._files is None:
            if self.staged:
                parts = self.git("diff", "--cached", "--raw", "--no-renames", "-z", "--diff-filter=ACMR").split("\0")
                # raw record: ":<src mode> <dst mode> <src sha> <dst sha> <status>" NUL path NUL; 160000 is a submodule
                self._files = sorted(p for meta, p in zip(parts[0::2], parts[1::2]) if p and meta.split()[1] != "160000")
            else:
                out = self.git("ls-files", "-z")
                self._files = sorted(p for p in out.split("\0") if p and (self.root / p).is_file())
        return self._files

    def read(self, rel: str) -> bytes:
        """File content: the staged blob with --staged (`git show :path`), the working tree otherwise."""
        if self.staged:
            return self._git_bytes(["show", f":{rel}"])
        return (self.root / rel).read_bytes()

    def size(self, rel: str) -> int:
        return len(self.read(rel)) if self.staged else (self.root / rel).stat().st_size

    def tool_root(self) -> Path:
        """Directory for external tools (ruff, bash, shellcheck, markdownlint): the checkout, or with --staged a
        copy of the staged blobs plus the tool configs, so the tools lint what will be committed."""
        if not self.staged:
            return self.root
        if self._tool_root is None:
            tmp = Path(tempfile.mkdtemp(prefix="gates-staged-"))
            atexit.register(shutil.rmtree, tmp, True)
            for rel in dict.fromkeys([*self.files, "ruff.toml", "pyproject.toml", "ci/ruff.toml", "ci/.markdownlint.jsonc"]):
                try:
                    data = self.read(rel)
                except GitError:  # not in the index: use the working-tree copy when there is one
                    if not (self.root / rel).is_file():
                        continue
                    data = (self.root / rel).read_bytes()
                dest = tmp / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            self._tool_root = tmp
        return self._tool_root

    def match(self, patterns: Iterable[str], rel: str) -> bool:
        return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(rel, p.rstrip("/") + "/*") for p in patterns)

    def md_files(self) -> list[str]:
        excl = self.cfg.get("md_exclude", [])
        return [f for f in self.files if f.endswith(".md") and not self.match(excl, f)]

    def text(self, rel: str) -> str:
        return self.read(rel).decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")

    def tool(self, name: str, gate_name: str) -> tuple[str | None, list[Finding]]:
        path = shutil.which(name)
        if path:
            return path, []
        return None, [Finding(gate_name, f"{name} not installed; check skipped" + (" (strict)" if self.strict else ""),
                              severity="error" if self.strict else "warn")]


def front(text: str) -> tuple[dict[str, str], dict[str, str]] | None:
    """(top-level keys, keys nested under `metadata:`) with scalar values only; None without frontmatter."""
    m = FRONT.match(text.replace("\r\n", "\n"))
    if not m:
        return None
    top: dict[str, str] = {}
    meta: dict[str, str] = {}
    in_meta = False
    for ln in m.group(1).split("\n"):
        if not ln.strip():
            continue
        indented = ln[:1] in " \t"
        k, _, v = ln.strip().partition(":")
        v = v.strip().strip("\"'")
        if not indented:
            in_meta = k == "metadata"
            if not in_meta:
                top[k] = v
        elif in_meta:
            meta[k] = v
    return top, meta


# --------------------------------------------------------------------------- repo hygiene

@gate("eol", "CRLF in the index breaks bash/python shebangs and makes every sync rewrite whole files")
def g_eol(c: Ctx):
    ga = c.root / ".gitattributes"
    if not ga.exists() or "eol=lf" not in ga.read_text(encoding="utf-8"):
        yield Finding("eol", ".gitattributes must set `* text=auto eol=lf`", ".gitattributes")
    keep = set(c.files)
    for row in c.git("ls-files", "--eol", "-z").split("\0"):
        meta, _, path = row.partition("\t")
        if path not in keep or not meta:
            continue
        idx = meta.split()[0]
        if idx in ("i/crlf", "i/mixed"):
            yield Finding("eol", f"index has {idx[2:].upper()} line endings (use LF; .ps1/.vbs get CRLF via .gitattributes)", path)


@gate("size", "a stray blob (log, export, model) bloats every clone forever; the sync already refuses >1 MB")
def g_size(c: Ctx):
    limit = c.cfg.get("max_file_bytes", 1_048_576)
    allow = c.cfg.get("size_allow", [])
    for f in c.files:
        n = c.size(f)
        if c.match(allow, f):
            continue
        if n > limit:
            yield Finding("size", f"{n} bytes > {limit}", f)
        elif n > limit // 2:
            yield Finding("size", f"{n} bytes, over half the {limit} limit", f, severity="warn")


@gate("paths", "Windows MAX_PATH (260) breaks clones of long paths; reserved names and case clashes break checkout")
def g_paths(c: Ctx):
    limit = c.cfg.get("max_path_len", 150)
    seen: dict[str, str] = {}
    lows = {x.lower() for x in c.files}
    for f in c.files:
        if len(f) > limit:
            yield Finding("paths", f"path is {len(f)} chars (> {limit}); clone dir + path must stay under 260", f)
        for part in f.split("/"):
            stem = part.split(".")[0].lower()
            if stem in WINDOWS_RESERVED or part.endswith((".", " ")) or re.search(r'[<>:"|?*]', part):
                yield Finding("paths", f"`{part}` is not a valid Windows file name", f)
        low = f.lower()
        if low in seen and seen[low] != f:
            yield Finding("paths", f"case-only clash with {seen[low]}", f)
        seen[low] = f
        segs = low.split("/")
        for i in range(1, len(segs)):
            parent = "/".join(segs[:i])
            if parent in lows:
                yield Finding("paths", f"`{parent}` is a file here and a directory in this path (case-insensitive clash; Windows cannot check out both)", f)


@gate("text", "BOM, invalid JSON and a missing final newline cause noisy diffs and parser surprises")
def g_text(c: Ctx):
    for f in c.files:
        if not f.endswith((".md", ".json", ".yml", ".yaml", ".py", ".sh", ".txt")):
            continue
        raw = c.read(f)
        if raw.startswith(b"\xef\xbb\xbf"):
            yield Finding("text", "UTF-8 BOM", f)
        if raw and not raw.endswith(b"\n"):
            yield Finding("text", "no newline at end of file", f, severity="warn")
        if f.endswith(".json"):
            try:
                json.loads(raw.decode("utf-8-sig"))
            except ValueError as e:
                yield Finding("text", f"invalid JSON: {e}", f)


@gate("exec-bit", "a .sh without the executable bit in the index fails on Linux after a Windows commit")
def g_exec(c: Ctx):
    modes = {}
    for r in c.git("ls-files", "-s", "-z").split("\0"):
        if "\t" in r:
            modes[r.split("\t", 1)[1]] = r.split()[0]
    for f in c.files:
        if f.endswith(".sh") and modes.get(f) != "100755":
            yield Finding("exec-bit", f"mode {modes.get(f)}; run `git update-index --chmod=+x {f}`", f)


# --------------------------------------------------------------------------- code

@gate("tests", "the offline suite is the contract of the tools; `python -I -m unittest` is the only runner")
def g_tests(c: Ctx):
    tdir = c.cfg.get("tests_dir", "tests")
    if not (c.root / "ci" / "test_gates.py").is_file():
        yield Finding("tests", "ci/test_gates.py is missing: the gates themselves have no tests", "ci/test_gates.py")
    if not (c.root / tdir).is_dir():
        yield Finding("tests", f"tests_dir `{tdir}` does not exist, so no test ran", tdir)
        return
    cmd = [sys.executable, "-I", "-m", "unittest", "discover", "-s", tdir]
    r = subprocess.run(cmd, cwd=c.root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stderr or "") + (r.stdout or "")
    m = re.search(r"^Ran (\d+) tests? in ", out, re.M)
    if r.returncode != 0 and (not m or int(m.group(1)) > 0):
        yield Finding("tests", "unittest failed:\n" + "\n".join(out.splitlines()[-25:]))
    elif not m or int(m.group(1)) == 0:
        yield Finding("tests", f"unittest ran 0 tests in `{tdir}`; an empty suite proves nothing", tdir)


@gate("python", "syntax errors and unused names caught before a sync job runs them at 09:00")
def g_python(c: Ctx):
    files = [x for x in c.files if x.endswith(".py")]
    for f in files:
        try:
            compile(c.text(f), f, "exec")
        except SyntaxError as e:
            yield Finding("python", f"syntax error: {e.msg}", f, e.lineno or 0)
    if not files:
        return
    ruff, miss = c.tool("ruff", "python")
    yield from miss
    if ruff:
        conf = ["--config", "ci/ruff.toml"] if (c.root / "ci" / "ruff.toml").exists() else []
        r = subprocess.run([ruff, "check", "--no-cache", *conf, *files], cwd=c.tool_root(), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            yield Finding("python", "ruff:\n" + r.stdout[-2500:])


@gate("shell", "bash -n and shellcheck catch the quoting bugs that delete or skip files in sync/restore scripts")
def g_shell(c: Ctx):
    sh = [f for f in c.files if f.endswith(".sh")]
    if not sh:
        return
    bash = shutil.which("bash")
    for f in sh:
        if bash:
            r = subprocess.run([bash, "-n", f], cwd=c.tool_root(), capture_output=True, text=True)
            if r.returncode:
                yield Finding("shell", "bash -n: " + r.stderr.strip()[:300], f)
    sc, miss = c.tool("shellcheck", "shell")
    yield from miss
    if sc:
        sev = c.cfg.get("shellcheck_severity", "warning")
        r = subprocess.run([sc, "-x", f"--severity={sev}", "-f", "gcc", *sh], cwd=c.tool_root(), capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        if r.returncode:
            yield Finding("shell", "shellcheck:\n" + r.stdout[-2500:])


# --------------------------------------------------------------------------- markdown

@gate("md-basic", "unbalanced code fences swallow the rest of a rule file; headings without a space are not headings")
def g_md_basic(c: Ctx):
    for f in c.md_files():
        fence = None
        for i, ln in enumerate(c.text(f).replace("\r\n", "\n").split("\n"), 1):
            m = re.match(r"^(\s*)(`{3,}|~{3,})", ln)
            if m:
                tok = m.group(2)
                if fence is None:
                    fence = (tok[0], len(tok), i)
                elif tok[0] == fence[0] and len(tok) >= fence[1]:
                    fence = None
            elif fence is None and re.match(r"^#{1,6}[^#\s]", ln):
                yield Finding("md-basic", "heading needs a space after #", f, i, "warn")
        if fence:
            yield Finding("md-basic", "code fence opened here is never closed", f, fence[2])


@gate("links", "a dead [[wikilink]] or relative link makes the agent chase a memory or file that is gone")
def g_links(c: Ctx):
    names = {Path(f).stem for f in c.md_files()} | {Path(f).name for f in c.files} | {Path(f).parent.name for f in c.files}
    names |= set(c.cfg.get("link_extra_names", []))
    wl_sev = "warn" if c.cfg.get("wikilinks_cross_layer", True) else "error"
    for f in c.md_files():
        body = FRONT.sub("", c.text(f).replace("\r\n", "\n"), count=1)
        body = re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"), body, flags=re.S)
        body = re.sub(r"`[^`\n]*`", "", body)
        for i, ln in enumerate(body.split("\n"), 1):
            for m in WIKILINK.finditer(ln):
                tgt = m.group(1).strip()
                if tgt not in names and tgt.rstrip("/") not in names:
                    yield Finding("links", f"[[{tgt}]] points to nothing in this repo", f, i, wl_sev)
            for m in MDLINK.finditer(ln):
                t = m.group(1)
                if re.match(r"^([a-z]+:|#|mailto:)", t, re.I) or t.startswith(("~", "$", "{")):
                    continue
                path = t.split("#")[0].split("?")[0]
                if path and not ((c.root / f).parent / path).exists():
                    yield Finding("links", f"relative link `{t}` does not exist", f, i)


def _mdlint_cmd():
    exe = shutil.which("markdownlint-cli2")
    if exe:
        return [exe]
    npx = shutil.which("npx")  # a bare "npx" does not resolve on Windows (npx.cmd)
    return [npx, "--yes", "markdownlint-cli2@0.14.0"] if npx else None


@gate("mdlint", "markdownlint keeps rule files consistent; CI installs it, locally it is optional")
def g_mdlint(c: Ctx):
    files = c.md_files()
    if not files:
        return
    sev = "error" if c.strict else "warn"
    if not (c.root / "ci" / ".markdownlint.jsonc").exists():
        yield Finding("mdlint", "ci/.markdownlint.jsonc is missing but the repo has Markdown files; they are not linted",
                      "ci/.markdownlint.jsonc", severity=sev)
        return
    cmd = _mdlint_cmd()
    if not cmd:
        yield Finding("mdlint", "markdownlint-cli2/npx not installed; check skipped", severity=sev)
        return
    r = subprocess.run([*cmd, "--config", "ci/.markdownlint.jsonc", *files], cwd=c.tool_root(), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        yield Finding("mdlint", "markdownlint:\n" + (r.stderr or r.stdout)[-3000:])


# --------------------------------------------------------------------------- frontmatter schemas

MEMORY_TYPES = {"user", "feedback", "project", "reference"}


@gate("memory-schema", "a memory with the wrong name/type/keywords is invisible to recall and to the lint that ranks them")
def g_memory(c: Ctx):
    cfg = c.cfg.get("memory", {})
    dirs = cfg.get("dirs", ["memory"])
    kmin, kmax = cfg.get("keywords", [6, 15])
    for f in c.files:
        p = Path(f)
        if p.suffix != ".md" or p.name == "MEMORY.md" or p.parts[0] not in dirs or len(p.parts) < 3:
            continue
        fm = front(c.text(f))
        if fm is None:
            yield Finding("memory-schema", "no frontmatter", f)
            continue
        top, meta = fm
        if top.get("name") != p.stem:
            yield Finding("memory-schema", f"name `{top.get('name')}` != filename `{p.stem}`", f)
        if not top.get("description"):
            yield Finding("memory-schema", "description missing", f)
        if cfg.get("require_level", True) and top.get("level") != c.cfg.get("level"):
            yield Finding("memory-schema", f"level `{top.get('level')}` != layer `{c.cfg.get('level')}`", f)
        t = meta.get("type") or top.get("type")
        if t not in MEMORY_TYPES:
            yield Finding("memory-schema", f"metadata.type `{t}` not in {sorted(MEMORY_TYPES)}", f)
        kw = [k for k in re.split(r",\s*", meta.get("keywords", "")) if k.strip()]
        if not kmin <= len(kw) <= kmax:
            yield Finding("memory-schema", f"{len(kw)} keywords (want {kmin}-{kmax})", f, severity="warn")
        mod = meta.get("modified") or top.get("modified")
        if not mod or not re.match(r"^\d{4}-\d{2}-\d{2}$", mod):
            yield Finding("memory-schema", "metadata.modified missing or not YYYY-MM-DD", f, severity="warn")


@gate("skill-schema", "skills are loaded by name+description; a name != directory or a long description is silently dropped")
def g_skill(c: Ctx):
    cfg = c.cfg.get("skills", {})
    maxd = cfg.get("max_description", 300)
    for f in c.files:
        p = Path(f)
        if p.name != "SKILL.md" or p.parts[0] not in cfg.get("dirs", ["skills"]) or len(p.parts) != 3:
            continue
        fm = front(c.text(f))
        if fm is None:
            yield Finding("skill-schema", "no frontmatter", f)
            continue
        top, _ = fm
        if top.get("name") != p.parent.name:
            yield Finding("skill-schema", f"name `{top.get('name')}` != directory `{p.parent.name}`", f)
        d = top.get("description", "")
        if not d:
            yield Finding("skill-schema", "description missing", f)
        elif len(d) > maxd and not c.match(cfg.get("long_description_allow", []), f):
            yield Finding("skill-schema", f"description is {len(d)} chars (> {maxd})", f,
                          severity="warn" if cfg.get("description_warn_only") else "error")
        if cfg.get("require_level", True) and top.get("level") != c.cfg.get("level"):
            yield Finding("skill-schema", f"level `{top.get('level')}` != layer `{c.cfg.get('level')}`", f)


# --------------------------------------------------------------------------- data leaks

SECRET_PATTERNS = [
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("age-secret-key", re.compile(r"AGE-SECRET-KEY-1[0-9A-Z]{50,}")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("api-key", re.compile(r"\b(?:sk|rk)-[A-Za-z0-9_-]{24,}")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{20,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
]


def scan(c: Ctx, gate_name: str, patterns, allow_paths, skip: Iterable[str] = ()) -> Iterable[Finding]:
    """Line scan of every tracked text file; the matched text is shown only for non-secret gates."""
    for f in c.files:
        if c.match(allow_paths, f) or f in skip:
            continue
        raw = c.read(f)
        if b"\0" in raw[:2048]:
            continue
        for i, ln in enumerate(raw.decode("utf-8", "replace").split("\n"), 1):
            for pname, rx in patterns:
                m = rx.search(ln)
                if m:
                    shown = f" `{m.group(0)[:40]}`" if gate_name == "deny" else ""
                    yield Finding(gate_name, f"{pname}{shown}", f, i)


DENY_SKIP = ("ci/config.json",)  # holds the deny patterns themselves; the secrets gate has no such exclusion


def baseline(c: Ctx, key: str) -> set[str]:
    p = c.cfg.get(key)
    if not p or not (c.root / p).exists():
        return set()
    return {ln.strip() for ln in c.text(p).splitlines() if ln.strip() and not ln.startswith("#")}


@gate("secrets", "a leaked token in a private repo is still a leaked token; gitleaks runs in CI, this runs offline")
def g_secrets(c: Ctx):
    yield from scan(c, "secrets", SECRET_PATTERNS, c.cfg.get("secrets_allow", []))


@gate("deny", "the layer boundary: terms that belong to another layer (machine paths, names, company) must not appear here")
def g_deny(c: Ctx):
    dl = c.cfg.get("denylist", {})
    pats = [(p["name"], re.compile(p["regex"], re.I if p.get("ignore_case", True) else 0)) for p in dl.get("patterns", [])]
    if not pats:
        return
    # ci/deny-baseline.txt lists known violations still being cleaned up ("<path>\t<pattern>" or "<path>\t*"):
    # they are reported as warnings, so the gate can only ratchet down.
    base = baseline(c, "deny_baseline")
    for fd in scan(c, "deny", pats, dl.get("allow_paths", []), skip=DENY_SKIP):
        pname = fd.msg.split(" ")[0]
        if f"{fd.path}\t{pname}" in base or f"{fd.path}\t*" in base:
            fd.severity = "warn"
        yield fd


@gate("commit-title", "squash merges use the PR title; Conventional Commits keep history readable and sync groups parseable")
def g_title(c: Ctx):
    title = c.title or os.environ.get("PR_TITLE")
    if not title:
        return
    title = title.strip()
    if not title_ok(title):
        yield Finding("commit-title", f"`{title[:120]}` is not Conventional Commits (type(scope): subject, {MAX_TITLE} chars at most in total)")


# --------------------------------------------------------------------------- runner

def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated gate names")
    ap.add_argument("--skip", help="comma-separated gate names")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--title", help="PR title for the commit-title gate (or $PR_TITLE)")
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(argv)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.modules.setdefault("gates", sys.modules[__name__])  # `from gates import gate` must see this module, not a copy
    try:
        import repo_gates  # noqa: F401  (registers repo-specific gates)
    except ModuleNotFoundError as e:
        if e.name != "repo_gates":
            raise
    cfg = load_config()
    if a.list:
        for n, (_, why) in GATES.items():
            print(f"{n:16} {why}")
        return 0

    ctx = Ctx(Path(a.root), cfg, a.staged, a.strict, a.title)

    def names(s: str) -> list[str]:
        return [x.strip() for x in s.split(",") if x.strip()]

    asked = names(a.only or "") + names(a.skip or "")
    unknown = [n for n in asked if n not in GATES]
    if unknown or (a.only is not None and not names(a.only)):
        print(f"[ERROR] unknown or empty gate selection {unknown or '(empty --only)'}; known gates: {', '.join(GATES)}", file=sys.stderr)
        return 2
    enabled = [n for n in GATES if n not in set(cfg.get("disabled", []))]
    if a.only is not None:
        enabled = names(a.only)
    if a.skip:
        enabled = [n for n in enabled if n not in names(a.skip)]
    if not ctx.staged and not set(enabled) <= {"commit-title"}:
        try:
            if not ctx.files:
                print("[ERROR] no tracked files in this repository; a run that checks nothing must not pass", file=sys.stderr)
                return 1
        except GitError as e:
            print(f"[ERROR] cannot list tracked files: {e}", file=sys.stderr)
            return 1

    gh = os.environ.get("GITHUB_ACTIONS") == "true"
    rows, failed = [], False
    for n in enabled:
        try:
            fs = list(GATES[n][0](ctx) or [])
        except GitError as e:
            fs = [Finding(n, f"git failed, the gate could not run: {e}")]
        errs = [f for f in fs if f.severity == "error"]
        warns = [f for f in fs if f.severity == "warn"]
        failed |= bool(errs)
        rows.append((n, len(errs), len(warns)))
        for f in errs + warns:
            loc = f"{f.path}:{f.line}" if f.path and f.line else f.path
            if gh:
                print(f"::{'error' if f.severity == 'error' else 'warning'} file={f.path},line={f.line or 1},title={n}::{f.msg.splitlines()[0]}")
            print(f"[{f.severity.upper():5}] {n:14} {loc + ' ' if loc else ''}{f.msg}")
    print("\n" + f"{'gate':16} {'errors':>6} {'warns':>6}")
    for n, e, w in rows:
        print(f"{n:16} {e:>6} {w:>6}  {'FAIL' if e else 'ok'}")
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as fh:
            fh.write("| gate | errors | warnings |\n|---|---|---|\n")
            fh.writelines(f"| {n} | {e} | {w} |\n" for n, e, w in rows)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
