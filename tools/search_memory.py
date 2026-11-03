#!/usr/bin/env python3
"""Search and index over Claude's context: memories of every project, global rules and skills.

Usage:
  python -I tools/search_memory.py "eval gate jev" [-k 8] [--root ~/.claude]
  python -I tools/search_memory.py --build [--quiet] [--force]   # rebuild the index (ingest step); skipped when current

Ranking is BM25 over weighted fields (name 3, keywords 3, description 2, body 1), accent and case
insensitive, with a light plural stem. Query words that the glossary marks as collisions
(`~/.claude/ubiquitous-language.md`, e.g. "brain") also search their standard terms at half weight.

The default personal home keeps the legacy repo index and catalog. Other roots keep both under
`<root>/.search-memory/`. `--root` overrides the selected home; otherwise CLAUDE_CONFIG_DIR or
the company associated with CODEX_HOME selects it. No source data crosses roots.
"""
import argparse
import fnmatch
import hashlib
import json
import math
import ntpath
import os
import re
import sys
import unicodedata
from pathlib import Path
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ospaths import long_path  # noqa: E402

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
INDEX_PATH = os.path.join(REPO, "index", "search-index.json")
CATALOG_PATH = os.path.join(REPO, "INDEX.md")
INDEX_VERSION = 3
BODY_STORED = 400  # chars of body kept in the index (jev_search --with-body sends the first 400)
FIELD_WEIGHTS = {"name": 3.0, "keywords": 3.0, "description": 2.0, "body": 1.0}
ALIAS_WEIGHT = 0.5
K1, B = 1.2, 0.75
STOPWORDS_EN = {"the", "and", "for", "with", "of", "to", "in", "on", "is", "it", "be", "how", "what", "who", "why",
                "a", "an", "are", "at", "by", "from", "this", "that"}
# Portuguese stopwords: data for memories written in Portuguese, kept so existing indexes rank the same way.
STOPWORDS_PT = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas", "um", "uma",
    "para", "pra", "pro", "por", "com", "sem", "que", "se", "qual", "quais", "como", "quem", "porque", "por que",
}
STOPWORDS = STOPWORDS_EN | STOPWORDS_PT
FRONT = re.compile(r"^---\n(.*?)\n---\n", re.S)
LINK = re.compile(r"\[\[([^\]]+)\]\]")


@dataclass
class Doc:
    path: str
    kind: str  # memory | rule | skill
    name: str
    description: str
    body: str
    keywords: str = ""
    project: str = ""
    links: list[str] = field(default_factory=list)


@dataclass
class Hit:
    doc: Doc
    score: float


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def stem(word: str) -> str:
    if len(word) > 4 and word.endswith("es") and not word.endswith("ses"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9_-]*", normalize(text))
    return [stem(w) for w in words if w not in STOPWORDS and len(w) > 1]


def _field(front: str, key: str) -> str:
    m = re.search(rf"^\s*{key}:\s*(.+)$", front, re.M)
    return m.group(1).strip().strip("\"'") if m else ""


def _read(path: str, kind: str, root: str = "") -> Doc:
    with open(long_path(path), encoding="utf-8", errors="replace") as fh:
        text = fh.read().replace("\r\n", "\n")
    m = FRONT.match(text)
    front, body = (m.group(1), text[m.end():]) if m else ("", text)
    if kind == "skill-reference":
        default_name = os.path.relpath(path, root).replace(os.sep, "/")
    elif kind == "skill":
        default_name = os.path.basename(os.path.dirname(path))
    else:
        default_name = os.path.splitext(os.path.basename(path))[0]
    project = ""
    if kind == "memory":
        project = os.path.basename(os.path.dirname(os.path.dirname(path))).split("-Codes-")[-1].strip("-") or "Codes"
    return Doc(path, kind, _field(front, "name") or default_name, _field(front, "description"), body,
               _field(front, "keywords"), project, sorted(set(LINK.findall(body))))


def default_root() -> str:
    """Resolve the active Claude home, failing closed for an unmapped custom Codex home."""
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        return os.path.abspath(os.path.expanduser(os.environ["CLAUDE_CONFIG_DIR"]))
    codex = os.environ.get("CODEX_HOME")
    if codex and os.path.normcase(os.path.abspath(os.path.expanduser(codex))) != os.path.normcase(os.path.expanduser("~/.codex")):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import companies
        data = companies.load()
        matches = [name for name in data["companies"]
                   if (home := companies.home_of(name, "codex", data)) and companies.norm(home) == companies.norm(codex)]
        if len(matches) != 1 or not (home := companies.home_of(matches[0], "claude", data)):
            raise ValueError("CODEX_HOME has no unique company Claude home; set CLAUDE_CONFIG_DIR or --root")
        return str(home.resolve())
    return os.path.expanduser("~/.claude")


def resolve_root(explicit: str | None = None) -> str:
    """Resolve and validate one existing context root; an explicit path takes precedence."""
    root = _logical_path(os.path.abspath(os.path.expanduser(explicit or default_root())))
    if not os.path.isdir(long_path(root)):
        raise ValueError(f"root does not exist: {root}")
    return root


def state_paths(root: str) -> tuple[str, str]:
    """Keep the legacy default location; every other root owns its derived files."""
    if os.path.normcase(os.path.realpath(os.path.expanduser(root))) == os.path.normcase(os.path.realpath(os.path.expanduser("~/.claude"))):
        return INDEX_PATH, CATALOG_PATH
    directory = Path(root).expanduser().resolve() / ".search-memory"
    return str(directory / "search-index.json"), str(directory / "INDEX.md")


def _logical_path(path: str) -> str:
    if os.name == "nt":
        if path[:8].lower() == "\\\\?\\unc\\":
            return "\\\\" + path[8:]
        if path.startswith("\\\\?\\"):
            return path[4:]
    return path


def _within(path: str, directory: str) -> bool:
    target = _logical_path(os.path.realpath(long_path(path), strict=True))
    base = _logical_path(os.path.realpath(long_path(directory), strict=True))
    return os.path.normcase(os.path.commonpath((target, base))) == os.path.normcase(base)


def _auxiliary_entry(entry: object) -> tuple[str, str, list[str]]:
    if not isinstance(entry, dict):
        raise ValueError("invalid search source entry")
    kind = entry.get("kind")
    keys = {"path", "kind", "role", "reason"} | ({"parent_skill"} if kind == "skill-reference" else set())
    if (set(entry) != keys or kind not in ("rule", "skill-reference")
            or entry.get("role") not in ("guidance", "reference")
            or not isinstance(entry.get("reason"), str) or not entry["reason"].strip()
            or not isinstance(entry.get("path"), str)):
        raise ValueError("invalid search source entry")
    relative = entry["path"].replace("\\", "/")
    parts = relative.split("/")
    if (ntpath.splitdrive(relative)[0] or relative.startswith("/") or any(p in ("", ".", "..") for p in parts)
            or not relative.lower().endswith(".md") or parts[-1].lower() in ("claude.md", "agents.md", "memory.md", "index.md")):
        raise ValueError("invalid search source path")
    return relative, kind, parts


def _auxiliary_owner(root: str, entry: dict, kind: str, parts: list[str]) -> str:
    path = os.path.join(root, *parts)
    if kind == "rule":
        if len(parts) != 1 or not _within(path, root):
            raise ValueError("rule must be a root document within the selected root")
    else:
        parent = entry["parent_skill"]
        if (not isinstance(parent, str) or len(parts) < 4 or parts[:3] != ["skills", parent, "references"]
                or parent in ("", ".", "..") or "/" in parent or "\\" in parent):
            raise ValueError("invalid skill reference parent")
        skill = os.path.join(root, "skills", parent)
        with open(long_path(os.path.join(skill, "SKILL.md")), "rb"):
            pass
        if not _within(path, skill):
            raise ValueError("skill reference escapes its registered skill")
    return path


def source_manifests(root: str) -> list[str]:
    """Each layer can own a fragment without exporting another layer's private catalog."""
    manifest = os.path.join(root, "search-sources.json")
    paths = [manifest] if os.path.lexists(long_path(manifest)) else []
    folder = os.path.join(root, "search-sources.d")
    paths.extend(os.path.join(folder, e.name) for e in _entries(folder)
                 if not e.name.startswith(".") and e.name.endswith(".json"))
    return sorted(paths)


def _auxiliary_config(manifest: str) -> list[dict]:
    with open(long_path(manifest), encoding="utf-8") as fh:
        config = json.load(fh)
    if (not isinstance(config, dict) or set(config) != {"version", "documents"}
            or type(config["version"]) is not int or config["version"] != 1
            or not isinstance(config["documents"], list)):
        raise ValueError("invalid search sources manifest")
    return config["documents"]


def auxiliary_sources(root: str) -> list[tuple[str, str]]:
    """Explicit reviewed sources; stale configuration stops the build instead of reducing coverage."""
    found, seen = [], set()
    for manifest in source_manifests(root):
        for entry in _auxiliary_config(manifest):
            relative, kind, parts = _auxiliary_entry(entry)
            key = os.path.normcase(relative)
            if key in seen:
                raise ValueError("duplicate search source path")
            seen.add(key)
            found.append((_auxiliary_owner(root, entry, kind, parts), kind))
    return found


def sources(root: str) -> list[tuple[str, str]]:
    found = []
    projects = os.path.join(root, "projects")
    for project in _entries(projects):
        if not project.name.startswith(".") and project.is_dir():
            memory = os.path.join(projects, project.name, "memory")
            found.extend((os.path.join(memory, entry.name), "memory") for entry in _entries(memory)
                         if not entry.name.startswith(".") and fnmatch.fnmatch(entry.name, "*.md")
                         and entry.name != "MEMORY.md")
    for folder in ("rules", "global"):
        directory = os.path.join(root, folder)
        found.extend((os.path.join(directory, entry.name), "rule") for entry in _entries(directory)
                     if not entry.name.startswith(".") and fnmatch.fnmatch(entry.name, "*.md"))
    skills = os.path.join(root, "skills")
    for skill in _entries(skills):
        if not skill.name.startswith(".") and skill.is_dir():
            path = os.path.join(skills, skill.name, "SKILL.md")
            if os.path.lexists(long_path(path)):
                found.append((path, "skill"))
    return sorted(found + auxiliary_sources(root))


def _entries(path: str) -> list[os.DirEntry]:
    """Enumerate a literal directory, including Windows directories beyond MAX_PATH."""
    try:
        with os.scandir(long_path(path)) as entries:
            return list(entries)
    except FileNotFoundError:
        return []


_REPORTED: set[str] = set()


def readable_sources(root: str) -> list[tuple[str, str]]:
    """`sources` minus the files this process cannot stat. One unreadable file must not stop the whole index:
    each is reported once on stderr and left out. A path over Windows MAX_PATH is not a reason to skip it:
    `long_path` reaches it."""
    ok = []
    for path, kind in sources(root):
        try:
            os.stat(long_path(path))
        except OSError as exc:
            if path not in _REPORTED:
                _REPORTED.add(path)
                print(f"search_memory: skipped {path} ({len(path)} chars): {exc}", file=sys.stderr)
            continue
        ok.append((path, kind))
    return ok


def glossary_aliases(root: str) -> dict[str, list[str]]:
    """Collision table of the glossary: each word maps to the tokens of its standard terms."""
    path = os.path.join(root, "ubiquitous-language.md")
    if not os.path.exists(long_path(path)):
        return {}
    aliases: dict[str, list[str]] = {}
    with open(long_path(path), encoding="utf-8") as fh:
        for line in fh:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) != 3 or not cells[2].count("**"):
                continue
            standard = " ".join(re.findall(r"\*\*([^*]+)\*\*", cells[2]) + re.findall(r'"([^"]+)"', cells[2]))
            for word in re.split(r"\s*/\s*", cells[0]):
                for t in tokens(word):
                    aliases[t] = sorted(set(aliases.get(t, [])) | (set(tokens(standard)) - {t}))
    return aliases


def _weighted_tf(doc: Doc) -> dict[str, float]:
    tf: dict[str, float] = {}
    for name, weight in FIELD_WEIGHTS.items():
        for t in tokens(getattr(doc, name)):
            tf[t] = tf.get(t, 0.0) + weight
    return tf


def source_fingerprint(root: str) -> str:
    """Hash paths and content, including the optional glossary, independent of timestamps."""
    paths = [p for p, _ in readable_sources(root)]
    glossary = os.path.join(root, "ubiquitous-language.md")
    if os.path.isfile(long_path(glossary)):
        paths.append(glossary)
    paths.extend(source_manifests(root))
    digest = hashlib.sha256()
    for path in sorted(paths):
        encoded = os.fsencode(path)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        with open(long_path(path), "rb") as fh:
            content = hashlib.file_digest(fh, "sha256").digest()
        digest.update(content)
    return digest.hexdigest()


def build(root: str) -> dict:
    fingerprint = source_fingerprint(root)
    docs = [_read(p, kind, root) for p, kind in readable_sources(root)]
    entries, df = [], {}
    for d in docs:
        tf = _weighted_tf(d)
        for t in tf:
            df[t] = df.get(t, 0) + 1
        # tf above used the whole body; the stored copy only feeds snippets and the catalog's first line
        entries.append({**d.__dict__, "body": d.body[:BODY_STORED], "tf": tf, "length": sum(tf.values())})
    backlinks: dict[str, list[str]] = {}
    for e in entries:
        for target in e["links"]:
            backlinks.setdefault(target, []).append(e["name"])
    for e in entries:
        e["backlinks"] = sorted(backlinks.get(e["name"], []))
    avgdl = sum(e["length"] for e in entries) / max(len(entries), 1)
    newest = _newest(root)  # every source, the glossary included, or the index would look stale forever
    if source_fingerprint(root) != fingerprint:
        raise RuntimeError("sources changed during index build; retry the operation")
    return {"version": INDEX_VERSION, "root": os.path.abspath(root), "newest_source": newest,
            "fingerprint": fingerprint,
            "aliases": glossary_aliases(root), "df": df, "avgdl": avgdl, "docs": entries}


def _newest(root: str) -> float:
    newest = max([os.path.getmtime(long_path(p)) for p, _ in readable_sources(root)] + [0.0])
    gloss = os.path.join(root, "ubiquitous-language.md")
    if os.path.exists(long_path(gloss)):
        newest = max(newest, os.path.getmtime(long_path(gloss)))
    newest = max([newest] + [os.path.getmtime(long_path(p)) for p in source_manifests(root)])
    return newest


def cached_index(root: str, path: str | None = None) -> dict | None:
    """The index on disk if it is current for this root: same version and root, same set of source files,
    unchanged source content and no source (or the glossary) newer than it."""
    path = path or state_paths(root)[0]
    newest = _newest(root)
    try:
        with open(long_path(path), encoding="utf-8") as fh:
            index = json.load(fh)
        known = sorted(e["path"] for e in index.get("docs", []))
        if (index.get("version") == INDEX_VERSION and index.get("root") == os.path.abspath(root)
                and known == sorted(p for p, _ in readable_sources(root))
                and index.get("newest_source", 0) >= newest and os.path.getmtime(long_path(path)) >= newest
                and index.get("fingerprint") == source_fingerprint(root)):
            return index
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def load_index(root: str, path: str | None = None) -> dict:
    """Cached index if it is current for this root, else a fresh build (not written to disk)."""
    return cached_index(root, path) or build(root)


def _bm25(tf: float, df: int, n: int, length: float, avgdl: float) -> float:
    idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
    return idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * length / avgdl))


def search(query: str, root: str, k: int = 8, index: dict | None = None) -> list[Hit]:
    index = index or load_index(root)
    query_terms = {t: 1.0 for t in tokens(query)}
    for t in list(query_terms):
        for alias in index["aliases"].get(t, []):
            query_terms.setdefault(alias, ALIAS_WEIGHT)
    n, avgdl, df = len(index["docs"]), index["avgdl"] or 1.0, index["df"]
    hits = []
    for e in index["docs"]:
        s = sum(w * _bm25(e["tf"][t], df[t], n, e["length"], avgdl)
                for t, w in query_terms.items() if t in e["tf"])
        if s > 0:
            doc = Doc(**{key: e[key] for key in Doc.__dataclass_fields__})
            hits.append(Hit(doc, round(s, 2)))
    hits.sort(key=lambda h: (-h.score, h.doc.path))
    return hits[:k]


def catalog(index: dict) -> str:
    lines = ["# Index of Claude's context", "",
             "Generated by `tools/search_memory.py --build` on every sync and every memory write. Do not edit.", ""]
    memories = [e for e in index["docs"] if e["kind"] == "memory"]
    for project in sorted({e["project"] for e in memories}):
        lines += [f"## Memory · {project}", ""]
        for e in sorted((e for e in memories if e["project"] == project), key=lambda e: e["name"]):
            extra = f" Keywords: {e['keywords']}." if e["keywords"] else ""
            back = f" Linked from: {', '.join(e['backlinks'])}." if e["backlinks"] else ""
            lines.append(f"- **{e['name']}**: {e['description'].rstrip('.')}.{extra}{back}")
        lines.append("")
    for kind, title in (("rule", "Global rules"), ("skill", "Skills"), ("skill-reference", "Skill references")):
        lines += [f"## {title}", ""]
        lines += [f"- **{e['name']}**: {(e['description'] or next(iter(e['body'].strip().splitlines()), e['name']))[:200]}"
                  for e in sorted((e for e in index["docs"] if e["kind"] == kind), key=lambda e: e["name"])]
        lines.append("")
    missing = sorted(e["name"] for e in memories if not e["keywords"])
    lines += ["## Memories without keywords", "", ", ".join(missing) or "None.", ""]
    return "\n".join(lines)


def _write_atomic(path: str, text: str) -> None:
    os.makedirs(long_path(os.path.dirname(path)), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(long_path(tmp), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(long_path(tmp), long_path(path))


def write_index(root: str, force: bool = False, index_path: str | None = None, catalog_path: str | None = None) -> tuple[dict, bool]:
    """Build and write the index and the catalog. Returns (index, rebuilt); nothing is rewritten when the
    index on disk is current and the catalog exists, unless `force`."""
    default_index, default_catalog = state_paths(root)
    index_path, catalog_path = index_path or default_index, catalog_path or default_catalog
    if not force and os.path.exists(long_path(catalog_path)):
        current = cached_index(root, index_path)
        if current is not None:
            return current, False
    index = build(root)
    _write_atomic(index_path, json.dumps(index, ensure_ascii=False))
    _write_atomic(catalog_path, catalog(index))
    return index, True


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?")
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--root", help="source home (overrides environment)")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--force", action="store_true", help="with --build: rebuild even if no source is newer")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    try:
        args.root = resolve_root(args.root)
    except (OSError, ValueError, KeyError) as exc:
        ap.error(str(exc))
    if args.build:
        index, rebuilt = write_index(args.root, args.force)
        if not args.quiet:
            if rebuilt:
                print(f"indexed {len(index['docs'])} files, {len(index['df'])} terms, {len(index['aliases'])} glossary aliases")
            else:
                print(f"index is current ({len(index['docs'])} files); nothing rebuilt (use --force)")
        return
    if not args.query:
        ap.error("give a query or --build")
    hits = search(args.query, args.root, args.k)
    if not hits:
        print("No match.")
    for h in hits:
        about = (h.doc.description or h.doc.name)[:160]
        print(f"{h.score:6.2f}  [{h.doc.kind}] {h.doc.path}\n        {about}")


if __name__ == "__main__":
    main()
