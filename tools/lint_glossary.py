#!/usr/bin/env python3
"""Check the glossaries of the context layers (the ubiquitous language of the agent). No model, no network.

Usage: python -I tools/lint_glossary.py --manifest ~/Codes/psique/manifest.json [--claude-home ~/.claude]
       python -I tools/lint_glossary.py --layer-dir DIR [--layer-dir DIR ...]   # repo trees (templates, tests)
    -> markdown report on stdout; exit 1 when there are problems.

Each layer names its glossary in layer.json (`"glossary": "<file>"`, also listed in `globals`). The file is a
markdown document in a fixed shape:

    # <title>
    Version: vN[.M], YYYY-MM-DD. ...
    ## Collisions (...)          table | Word | Senses | Standard term |
    ## Standard terms            bullets with **term**: definition (### sub-headings allowed)
    ## How to read requests      bullets with **expression**: reading

Problems (exit 1): glossary not declared, missing, not in globals, no version line, a required section
missing, a term defined in two layers with different texts and not listed as a collision anywhere, and a
superego glossary that names a term another layer owns (it must stay generic). Warnings (exit 0): the same
term with the same text in two layers (dedupe: always-loaded bytes), and a glossary over SIZE_WARN bytes.
"""
import argparse
import json
import os
import re
import sys

SECTIONS = ("Collisions", "Standard terms", "How to read requests")
# Legacy Portuguese headings and version line stay accepted: layers of an existing install may still use them.
VERSION = re.compile(r"^(?:Versão|Version):\s*v\d+(?:\.\d+)*,\s*(?:\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}|DD/MM/AAAA|YYYY-MM-DD)\.", re.M)
ALIASES = {"Collisions": ("Collisions", "Colisões"), "Standard terms": ("Standard terms", "Termos padrão"),
           "How to read requests": ("How to read requests", "Como interpretar pedidos")}
TERM = re.compile(r"\*\*([^*\n]{1,60})\*\*\s*(?:\([^)]*\)\s*)?[:=]")
HEADING = re.compile(r"^##\s+(.+?)\s*$", re.M)
ROW = re.compile(r"^\|\s*([^|]+?)\s*\|", re.M)
SIZE_WARN = 4096
ORDER = {"superego": 0, "persona": 1, "collective": 2, "ego": 3, "id": 4}


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read().replace("\r\n", "\n")


def sections(text: str) -> dict[str, str]:
    """{heading text: body} for the H2 sections of the document."""
    out: dict[str, str] = {}
    marks = list(HEADING.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out[m.group(1)] = text[m.end():end]
    return out


def section(secs: dict[str, str], name: str) -> str | None:
    names = ALIASES.get(name, (name,))
    for head, body in secs.items():
        if head.startswith(names):
            return body
    return None


def norm(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().strip('"').casefold())


def definitions(body: str) -> dict[str, str]:
    """term -> text up to the next bold term or line end, for the bullet sections."""
    out: dict[str, str] = {}
    for line in body.splitlines():
        matches = list(TERM.finditer(line))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(line)
            text = line[m.end():end].strip().rstrip(".").strip()
            out.setdefault(norm(m.group(1)), text)
    return out


def collisions(body: str) -> set[str]:
    words = set()
    for m in ROW.finditer(body):
        w = m.group(1)
        if w in ("Palavra", "---") or set(w) <= set("-: "):
            continue
        for part in re.split(r"\s*/\s*", w):
            words.add(norm(part))
    return words


class Layer:
    def __init__(self, level: str, name: str, path: str, cfg: dict):
        self.level, self.name, self.path, self.cfg = level, name, path, cfg
        self.glossary = cfg.get("glossary")
        self.text: str | None = None
        self.terms: dict[str, str] = {}
        self.collisions: set[str] = set()


def load_layers_from_manifest(manifest: str, home: str | None) -> list[Layer]:
    man = json.load(open(manifest, encoding="utf-8"))
    out = []
    for l in man["layers"]:
        if not l.get("active", True):
            continue
        path = os.path.normpath(os.path.expanduser(l["path"]))
        cfgp = os.path.join(path, "layer.json")
        cfg = json.load(open(cfgp, encoding="utf-8")) if os.path.isfile(cfgp) else {}
        layer = Layer(l["level"], l.get("name", ""), path, cfg)
        if layer.glossary:
            src = os.path.join(home, layer.glossary) if home else os.path.join(path, "global", layer.glossary)
            if os.path.isfile(src):
                layer.text = read(src)
        out.append(layer)
    return out


def load_layer_dirs(dirs: list[str]) -> list[Layer]:
    out = []
    for d in dirs:
        cfg = json.load(open(os.path.join(d, "layer.json"), encoding="utf-8"))
        layer = Layer(cfg.get("level", "?"), cfg.get("name", ""), os.path.normpath(d), cfg)
        if layer.glossary:
            # Templates name the file with a placeholder; the real file sits beside it with a plain name.
            cands = [os.path.join(d, "global", layer.glossary)]
            gdir = os.path.join(d, "global")
            if os.path.isdir(gdir):
                cands += [os.path.join(gdir, f) for f in sorted(os.listdir(gdir)) if f.startswith(("glossario", "glossary", "linguagem", "ubiquitous"))]
            for c in cands:
                if os.path.isfile(c):
                    layer.text = read(c)
                    break
        out.append(layer)
    return out


def check(layers: list[Layer]) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    warnings: list[str] = []
    for l in layers:
        who = f"`{l.level}` ({os.path.basename(l.path)})"
        if l.level == "persona" and not l.glossary:
            continue  # persona practices need no glossary of their own
        if not l.glossary:
            problems.append(f"- {who}: layer.json has no `glossary` field")
            continue
        if l.glossary not in l.cfg.get("globals", []):
            problems.append(f"- {who}: `{l.glossary}` is the glossary but is not listed in `globals` (it would not be loaded)")
        if l.text is None:
            problems.append(f"- {who}: glossary `{l.glossary}` not found")
            continue
        if not VERSION.search(l.text):
            problems.append(f"- {who}: no `Version: vN, YYYY-MM-DD.` line (legacy Portuguese `Versão: vN, DD/MM/AAAA.` also accepted)")
        secs = sections(l.text)
        for name in SECTIONS:
            if section(secs, name) is None:
                problems.append(f"- {who}: section `## {name}` missing")
        for name in ("Standard terms", "How to read requests"):
            body = section(secs, name)
            if body:
                l.terms.update(definitions(body))
        col = section(secs, "Collisions")
        if col:
            l.collisions = collisions(col)
        size = len(l.text.encode("utf-8"))
        if size > SIZE_WARN:
            warnings.append(f"- {who}: glossary is {size} bytes (over {SIZE_WARN}; it is always loaded)")
    layers = sorted([l for l in layers if l.text is not None], key=lambda l: ORDER.get(l.level, 9))
    all_collisions = set().union(*(l.collisions for l in layers)) if layers else set()
    for i, a in enumerate(layers):
        for b in layers[i + 1:]:
            for term in sorted(set(a.terms) & set(b.terms)):
                if a.terms[term] == b.terms[term]:
                    warnings.append(f"- `{term}`: same definition in {a.level} and {b.level} (keep it in one layer)")
                elif term not in all_collisions:
                    problems.append(f"- `{term}`: defined in {a.level} and {b.level} with different texts and not in any Collisions table")
    # The superego glossary stays generic: it may not name a term another layer owns.
    for sup in [l for l in layers if l.level == "superego"]:
        owned = {t: l.level for l in layers if l is not sup for t in l.terms if t not in sup.terms}
        for term, level in sorted(owned.items()):
            if len(term) < 4 or term in all_collisions:
                continue
            if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", sup.text, re.I):
                problems.append(f"- superego glossary mentions `{term}`, a term of the {level} layer (superego stays generic)")
    return problems, warnings


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest")
    ap.add_argument("--claude-home", help="read each glossary from ~/.claude (the source) instead of the repo copy")
    ap.add_argument("--layer-dir", action="append", default=[])
    args = ap.parse_args()
    if args.manifest:
        home = os.path.normpath(os.path.expanduser(args.claude_home)) if args.claude_home else None
        layers = load_layers_from_manifest(os.path.expanduser(args.manifest), home)
    elif args.layer_dir:
        layers = load_layer_dirs(args.layer_dir)
    else:
        ap.error("--manifest or --layer-dir is required")
    problems, warnings = check(layers)
    print("# Glossary lint report\n")
    print(f"{len(layers)} layers. {len(problems)} problems.\n")
    print("## Problems\n")
    print("\n".join(problems) or "None.")
    print(f"\n## Warnings ({len(warnings)}; not counted as problems)\n")
    print("\n".join(warnings) or "None.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
