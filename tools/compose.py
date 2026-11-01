#!/usr/bin/env python3
"""Compose ~/.claude from the layers: the root CLAUDE.md (generated, imports each layer's global files in
manifest order: superego, ego, id, then the harness adapter), the MEMORY.md index lines that a layered
restore may have left out, and the Codex render (tools/render_harness.py).

  python -I tools/compose.py [--manifest <root>/psique/manifest.json] [--claude-home ~/.claude] [--dry-run]
  python -I tools/compose.py --company NAME --out DIR [--manifest M] [--companies companies.json] [--codes DIR]

With --company the home for one company is composed into DIR (CLAUDE.md, AGENTS.md, global/, rules/, harness/),
read from the layer repos and never from ~/.claude: superego and id always, ego and collective only when they
belong to NAME; their skills/ folders are copied into DIR/skills (an ego layer of another company, or one with no `company`, is never read). The ego of NAME
is used even when its manifest entry is inactive; `active` only drives the default (no --company) mode.
Without --company nothing else in this file changes.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import companies  # noqa: E402
import layers  # noqa: E402
import roots  # noqa: E402

HEADER = """# Contexto do agente (gerado por psique; não edite, mude a camada)

Camadas, nesta ordem: superego (regras gerais de agente), collective (o time), ego (empresa), id (o
usuário). Em conflito vale id, depois ego, collective e superego. Cada camada traz o seu glossário. Onde um arquivo diz "o Claude", leia "o agente".
"""
FOOTER = """
## Harness
Nomes de ferramenta, de modelo e de hook ficam no adaptador do harness, em `~/.claude/harness/`.
@~/.claude/harness/claude.md
"""
TITLES = {"superego": "## Regras gerais (superego)", "persona": "## Persona (practices, opt-in)", "collective": "## Time (collective)", "ego": "## Empresa (ego)",
          "id": "## Usuário (id)"}
DESC = re.compile(r'^description:\s*"?(.*?)"?\s*$', re.M)
NAME = re.compile(r"^name:\s*(.+?)\s*$", re.M)


def root_claude_md(man: dict, home: str) -> str:
    parts = [HEADER]
    for layer in layers.active_layers(man):
        files = [f for f in layer["config"].get("globals", []) if f.endswith(".md") and os.path.isfile(os.path.join(home, f))]
        if not files:
            continue
        parts.append(TITLES.get(layer["level"], f"## {layer['level']}"))
        parts.extend(f"@~/.claude/{f}" for f in files)
        parts.append("")
    parts.append(FOOTER)
    return "\n".join(parts)


# --------------------------------------------------------------------------- one company

LEVEL_ORDER = ("superego", "persona", "collective", "ego", "id")  # load order; precedence is the reverse
SHARED_LEVELS = ("superego", "persona", "id")
COMPANY_FOOTER = """
## Harness
Nomes de ferramenta, de modelo e de hook ficam no adaptador do harness, em `harness/` desta pasta.
@./harness/claude.md
"""


def company_layers(man: dict, company: str, data: dict, codes: str = "", note=print) -> list[dict]:
    """Layers that may reach the home of `company`, in LEVEL_ORDER.

    superego and id: the active ones, for every company. ego and collective: only layers whose `company` is
    `company` (manifest entry, `active` ignored). A collective that the manifest does not list is found through
    companies.json (`collective` = folder name under `codes`) when that folder has a layer.json.
    """
    if company not in data["companies"]:
        raise SystemExit(f"unknown company {company!r}; known: {', '.join(sorted(data['companies'])) or 'none'}")
    chosen = []
    for layer in man["layers"]:
        level = layer["level"]
        if level in SHARED_LEVELS:
            if layer["active"]:
                chosen.append(layer)
        elif layer.get("company") == company:
            chosen.append(layer)
        else:
            note(f"skip {level} layer {layer.get('name', layer['path'])}: company {layer.get('company')!r}, not {company!r}")
    if not any(l["level"] == "collective" for l in chosen):
        folder = data["companies"][company].get("collective")
        path = layers.expand(os.path.join(codes or roots.layers_root(), folder)) if folder else ""
        cfg_path = os.path.join(path, "layer.json")
        if folder and os.path.isfile(cfg_path):
            chosen.append({"level": "collective", "name": folder, "path": path, "active": True,
                           "config": layers.read_json(cfg_path)})
    return sorted(chosen, key=lambda l: LEVEL_ORDER.index(l["level"]) if l["level"] in LEVEL_ORDER else len(LEVEL_ORDER))


def layer_files(layer: dict) -> tuple[list[str], list[str]]:
    """(globals .md, rules) of a layer repo that exist on disk, as paths relative to the repo."""
    cfg, root = layer["config"], layer["path"]
    gl = [f"global/{f}" for f in cfg.get("globals", []) if f.endswith(".md") and os.path.isfile(os.path.join(root, "global", f))]
    ru = [f"rules/{f}" for f in cfg.get("rules", []) if os.path.isfile(os.path.join(root, "rules", f))]
    return gl, ru


def layer_skills(layer: dict) -> list[str]:
    """Skill folders (with a SKILL.md) of a company layer; superego and id skills are not company-scoped."""
    if layer["level"] not in ("ego", "collective"):
        return []
    root = os.path.join(layer["path"], "skills")
    if not os.path.isdir(root):
        return []
    return sorted(n for n in os.listdir(root) if os.path.isfile(os.path.join(root, n, "SKILL.md")))


def company_claude_md(selected: list[dict]) -> str:
    parts = [HEADER]
    for layer in selected:
        gl, _ = layer_files(layer)
        if not gl:
            continue
        parts.append(TITLES.get(layer["level"], f"## {layer['level']}"))
        parts.extend(f"@./{f}" for f in gl)
        parts.append("")
    parts.append(COMPANY_FOOTER)
    return "\n".join(parts)


def budget_problems(man: dict, sizes: dict[str, int]) -> list[str]:
    budgets = man.get("budgets", {})
    return [f"{key}: {n} bytes, over its budget of {budgets[key]}" for key, n in sizes.items()
            if isinstance(budgets.get(key), int) and n > budgets[key]]


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


SKILL_MARKER = ".company-skills.json"


def claude_only_skills(superego: dict | None) -> set[str]:
    """Skills that exist only for Claude Code (superego harness/skills.json); Codex homes do not get them."""
    path = os.path.join(superego["path"], "harness", "skills.json") if superego else ""
    if not os.path.isfile(path):
        return set()
    return set(layers.read_json(path).get("claude_only", []))


def sync_company_skills(skills: dict[str, str], dst_root: str, own_all: bool, dry_run: bool = False, note=print) -> list[str]:
    """Copy skill folders into dst_root. Copied, not linked: no link can later point into another company.

    own_all: dst_root belongs to the composed home, so a skill that left the layers is removed.
    Otherwise (a Codex home that has skills of its own) only folders recorded in SKILL_MARKER are ever replaced or
    removed; a folder with the same name that is not recorded is left alone with a message.
    Returns the names written.
    """
    marker = os.path.join(dst_root, SKILL_MARKER)
    owned = set(layers.read_json(marker).get("skills", [])) if os.path.isfile(marker) else set()
    written = []
    for name in sorted(owned - set(skills)):
        note(f"{'would remove' if dry_run else 'remove'} skill {name}")
        if not dry_run:
            shutil.rmtree(os.path.join(dst_root, name), ignore_errors=True)
    if own_all and os.path.isdir(dst_root) and not dry_run:
        for name in os.listdir(dst_root):
            if name not in skills and os.path.isdir(os.path.join(dst_root, name)):
                shutil.rmtree(os.path.join(dst_root, name), ignore_errors=True)
    for name, src in sorted(skills.items()):
        dst = os.path.join(dst_root, name)
        if os.path.lexists(dst) and name not in owned and not own_all:
            note(f"skip skill {name}: a folder that is not ours already exists in {dst_root}")
            continue
        written.append(name)
        if dry_run:
            continue
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git"))
    if not own_all and not dry_run and (written or owned):
        write_text(marker, json.dumps({"skills": written}, indent=1) + chr(10))
    return written


def layer_sizes(selected: list[dict]) -> dict[str, int]:
    """Bytes of the always-loaded .md files of each layer (globals + rules), by level."""
    sizes: dict[str, int] = {}
    for layer in selected:
        for rel in sum(layer_files(layer), []):
            sizes[layer["level"]] = sizes.get(layer["level"], 0) + os.path.getsize(os.path.join(layer["path"], *rel.split("/")))
    return sizes


def default_layers(man: dict) -> list[dict]:
    """The layers of the default home (no --company): every active layer, in manifest order."""
    return layers.active_layers(man)


def composition_sizes(man: dict, selected: list[dict]) -> dict[str, int]:
    """Sizes by budget key for a set of layers: per level, the larger harness adapter, and the root CLAUDE.md."""
    sizes = layer_sizes(selected)
    superego = next((l for l in selected if l["level"] == "superego"), None)
    adapters = [os.path.join(superego["path"], "harness", f"{h}.md") for h in ("claude", "codex")] if superego else []
    sizes["adapter"] = max([os.path.getsize(p) for p in adapters if os.path.isfile(p)] or [0])  # the larger of the two harnesses
    sizes["root"] = len(company_claude_md(selected).encode("utf-8"))
    return sizes


def company_plan(man: dict, company: str, data: dict, codes: str = "", note=print) -> dict:
    """What the home of `company` contains: layers, files {rel: source}, skills {name: folder}, sizes, root text."""
    selected = company_layers(man, company, data, codes, note)
    superego = next((l for l in selected if l["level"] == "superego"), None)
    files: dict[str, str] = {}  # path relative to the home -> source file
    for layer in selected:
        gl, ru = layer_files(layer)
        for rel in gl + ru:
            if rel in files:
                raise SystemExit(f"{rel} exists in two layers ({files[rel]} and {layer['path']}); rename one")
            files[rel] = os.path.join(layer["path"], *rel.split("/"))
    skills: dict[str, str] = {}  # skill name -> source folder
    for layer in selected:
        for name in layer_skills(layer):
            if name in skills:
                raise SystemExit(f"skill {name} exists in two layers ({skills[name]} and {layer['path']}); rename one")
            skills[name] = os.path.join(layer["path"], "skills", name)
    for harness in ("claude", "codex"):
        src = os.path.join(superego["path"], "harness", f"{harness}.md") if superego else ""
        if os.path.isfile(src):
            files[f"harness/{harness}.md"] = src
    return {"selected": selected, "superego": superego, "files": files, "skills": skills,
            "sizes": composition_sizes(man, selected), "root_text": company_claude_md(selected)}


def compose_company(man: dict, company: str, data: dict, out: str, codes: str = "", dry_run: bool = False,
                    note=print) -> int:
    """Write the home of one company into `out` (see the module docstring). Returns a process exit code."""
    plan = company_plan(man, company, data, codes, note)
    selected, files, skills = plan["selected"], plan["files"], plan["skills"]
    problems = budget_problems(man, plan["sizes"])
    if problems:
        for p in problems:
            note("budget problem: " + p)
        note(f"{out} not written: a layer is over its byte budget (tools/context_budget.py)")
        return 1
    if dry_run:
        for rel in ["CLAUDE.md", "AGENTS.md", *sorted(files), *(f"skills/{n}/" for n in sorted(skills))]:
            note(f"would write {os.path.join(out, rel)}")
        return 0
    import render_harness  # noqa: E402  (lazy: render_harness imports this module for --company)

    for rel, src in files.items():
        with open(src, encoding="utf-8") as fh:
            write_text(os.path.join(out, *rel.split("/")), fh.read())
    sync_company_skills(skills, os.path.join(out, "skills"), own_all=True, note=note)
    write_text(os.path.join(out, "CLAUDE.md"), plan["root_text"])
    agents = render_harness.render_agents_md(out)
    write_text(os.path.join(out, "AGENTS.md"), agents)
    for folder in ("global", "rules", "harness"):  # drop files of a layer that no longer feeds this home
        for root, _, names in os.walk(os.path.join(out, folder)):
            for name in names:
                rel = os.path.relpath(os.path.join(root, name), out).replace(os.sep, "/")
                if rel not in files:
                    os.remove(os.path.join(root, name))
    note(f"composed {company}: {', '.join(l['level'] for l in selected)} -> {out} (AGENTS.md {len(agents.encode('utf-8'))} bytes)")
    return 0


def missing_index_lines(home: str) -> dict[str, list[str]]:
    """{MEMORY.md path: [lines to append]} for memories not yet listed in their project's index."""
    out: dict[str, list[str]] = {}
    projects = os.path.join(home, "projects")
    if not os.path.isdir(projects):
        return out
    for key in sorted(os.listdir(projects)):
        mem = os.path.join(projects, key, "memory")
        if not os.path.isdir(mem):
            continue
        idx = os.path.join(mem, "MEMORY.md")
        index = open(idx, encoding="utf-8").read() if os.path.isfile(idx) else ""
        for name in sorted(os.listdir(mem)):
            if not name.endswith(".md") or name == "MEMORY.md" or f"({name})" in index:
                continue
            head = open(os.path.join(mem, name), encoding="utf-8").read(2048)
            title = (NAME.search(head) or [None, name[:-3]])[1]
            desc = (DESC.search(head) or [None, ""])[1]
            out.setdefault(idx, []).append(f"- [{title}]({name}) — {desc}".rstrip(" —"))
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", help="default: <root>/psique/manifest.json")
    ap.add_argument("--root", help="folder holding the layer repos (default: $PSIQUE_ROOT, else the parent of this checkout)")
    ap.add_argument("--claude-home", default=os.path.expanduser("~/.claude"))
    ap.add_argument("--codex-home", default=os.path.expanduser("~/.codex"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--company", help="compose the home of one company (needs --out); see the module docstring")
    ap.add_argument("--out", help="with --company: folder to write the composed home into")
    ap.add_argument("--companies", help="with --company: companies.json (default ~/.claude/companies.json)")
    ap.add_argument("--codes", help="with --company: folder holding the layer repos (default: the root)")
    args = ap.parse_args()
    manifest = layers.expand(args.manifest or roots.default_manifest(args.root))
    if args.company:
        if not args.out:
            ap.error("--company needs --out")
        man = layers.load_manifest(manifest)
        return compose_company(man, args.company, companies.load(args.companies), layers.expand(args.out),
                               args.codes or roots.layers_root(args.root),
                               args.dry_run, note=lambda m: print(m, file=sys.stderr if m.startswith(("skip", "budget")) else sys.stdout))
    home = layers.expand(args.claude_home)
    man = layers.load_manifest(manifest)

    text = root_claude_md(man, home)
    path = os.path.join(home, "CLAUDE.md")
    old = open(path, encoding="utf-8").read() if os.path.isfile(path) else None
    if old != text:
        print(f"write {path}")
        if not args.dry_run:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
    for idx, lines in missing_index_lines(home).items():
        print(f"index {idx}: +{len(lines)} line(s)")
        if not args.dry_run:
            existing = open(idx, encoding="utf-8").read() if os.path.isfile(idx) else "# Memória\n\n"
            with open(idx, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(existing.rstrip("\n") + "\n" + "\n".join(lines) + "\n")
    render = os.path.join(os.path.dirname(os.path.abspath(__file__)), "render_harness.py")
    cmd = [sys.executable, "-I", render, "--claude-home", home, "--codex-home", layers.expand(args.codex_home)]
    if args.dry_run:
        cmd.append("--dry-run")
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    sys.exit(main())
