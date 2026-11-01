#!/usr/bin/env python3
"""Byte budget of the always-loaded context, per layer (the ubiquitous "AGENTS.md never fills up" rule).

Every file that reaches the Codex AGENTS.md (and the Claude CLAUDE.md imports) belongs to one layer: the
`.md` globals and the `rules` of each layer.json, the harness adapter (budget key "adapter"), and the root
CLAUDE.md (key "root"). psique/manifest.json carries the budgets:

    "budgets": {"superego": 12500, "collective": 2000, "ego": 6000, "id": 7000, "adapter": 2500, "root": 600}

They must sum to under the Codex limit (32,768) with headroom. A layer over its budget is a problem (the
render refuses to write, CI fails); over BAND (90%) is a warning (the daily job proposes trims to the
decision inbox with --inbox). A loaded file no layer owns is a problem too: nothing is always-loaded
without a budget.

  python -I tools/context_budget.py [--manifest M] [--claude-home H] [--json] [--inbox]
  python -I tools/context_budget.py --repo DIR [--base REF]   # one layer repo (CI): sizes of global/*.md and
                                                               # rules/*.md in the checkout, delta against REF
"""
import argparse
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python -I drops the script dir
import roots  # noqa: E402

LIMIT = 32768
BAND = 0.90
HEADROOM = 0.05  # the budgets together leave at least this share of the limit free


def nbytes(path: str) -> int:
    with open(path, "rb") as fh:
        return len(fh.read().replace(b"\r\n", b"\n"))


def expand(path: str) -> str:
    return os.path.normpath(os.path.expanduser(path))


def report(manifest_path: str, home: str, harness: str = "codex") -> dict:
    man = json.load(open(manifest_path, encoding="utf-8"))
    budgets = man.get("budgets", {})
    layers = {}
    owned: set[str] = set()
    for l in man["layers"]:
        if not l.get("active", True):
            continue
        cfgp = os.path.join(expand(l["path"]), "layer.json")
        cfg = json.load(open(cfgp, encoding="utf-8")) if os.path.isfile(cfgp) else {}
        files = []
        for g in cfg.get("globals", []):
            if g.endswith(".md"):
                p = os.path.join(home, g)
                if os.path.isfile(p):
                    files.append(p)
        for r in cfg.get("rules", []):
            p = os.path.join(home, "rules", r)
            if os.path.isfile(p):
                files.append(p)
        owned.update(os.path.normcase(f) for f in files)
        layers[l["level"]] = {"files": {os.path.relpath(f, home).replace(os.sep, "/"): nbytes(f) for f in files}}
    adapter = os.path.join(home, "harness", f"{harness}.md")
    layers["adapter"] = {"files": {f"harness/{harness}.md": nbytes(adapter)} if os.path.isfile(adapter) else {}}
    root = os.path.join(home, "CLAUDE.md")
    layers["root"] = {"files": {"CLAUDE.md": nbytes(root)} if os.path.isfile(root) else {}}
    owned.update(os.path.normcase(p) for p in (adapter, root))
    problems, warnings = [], []
    for key, info in layers.items():
        total = sum(info["files"].values())
        budget = budgets.get(key)
        info.update({"bytes": total, "budget": budget})
        if budget is None:
            if total:
                problems.append(f"{key}: {total} bytes loaded and no budget in the manifest")
            continue
        info["share"] = round(total / budget, 3) if budget else None
        if total > budget:
            problems.append(f"{key}: {total} bytes, over its budget of {budget} (trim {total - budget})")
        elif total > budget * BAND:
            warnings.append(f"{key}: {total} bytes, {total * 100 // budget}% of its budget of {budget}")
    unowned = [os.path.relpath(p, home).replace(os.sep, "/") for p in sorted(glob.glob(os.path.join(home, "rules", "*.md")))
               if os.path.normcase(p) not in owned]
    for p in unowned:
        problems.append(f"{p}: always loaded but no layer.json lists it (no budget)")
    total_budget = sum(v for v in budgets.values() if isinstance(v, int))
    if budgets and total_budget > LIMIT * (1 - HEADROOM):
        problems.append(f"budgets sum to {total_budget}, over {int(LIMIT * (1 - HEADROOM))} (limit {LIMIT} minus headroom)")
    return {"layers": layers, "budgets": budgets, "limit": LIMIT, "loaded": sum(l["bytes"] for l in layers.values()),
            "problems": problems, "warnings": warnings, "unowned": unowned}


def repo_sizes(repo: str, ref: str | None = None) -> dict[str, int]:
    """Bytes of global/*.md and rules/*.md in a layer repo checkout, or at a git ref."""
    out: dict[str, int] = {}
    if ref is None:
        for pat in ("global/*.md", "rules/*.md"):
            for p in sorted(glob.glob(os.path.join(repo, pat))):
                out[os.path.relpath(p, repo).replace(os.sep, "/")] = nbytes(p)
        return out
    ls = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--name-only", ref, "global", "rules"],
                        capture_output=True, text=True, encoding="utf-8")
    for name in ls.stdout.split():
        if name.endswith(".md"):
            blob = subprocess.run(["git", "-C", repo, "show", f"{ref}:{name}"], capture_output=True)
            if blob.returncode == 0:
                out[name] = len(blob.stdout.replace(b"\r\n", b"\n"))
    return out


def print_report(rep: dict) -> None:
    print(f"Always-loaded context: {rep['loaded']} bytes of {rep['limit']} ({rep['loaded'] * 100 // rep['limit']}%).")
    for key, info in rep["layers"].items():
        b = info["budget"]
        head = f"- {key}: {info['bytes']} bytes" + (f" / budget {b} ({info['bytes'] * 100 // b}%)" if b else " / no budget")
        print(head)
        for f, n in sorted(info["files"].items(), key=lambda kv: -kv[1]):
            print(f"    {f}={n}")
    print("\nProblems:\n" + ("\n".join("- " + p for p in rep["problems"]) or "None."))
    print("\nWarnings:\n" + ("\n".join("- " + w for w in rep["warnings"]) or "None."))


def add_inbox_items(rep: dict, home: str) -> list[str]:
    """One open inbox item per layer in the band or over budget (the daily job calls this)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import decisions  # noqa: E402

    added = []
    with decisions.locked(home):
        data = decisions.load(home)
        for msg in rep["problems"] + rep["warnings"]:
            key = msg.split(":")[0]
            if key not in rep["layers"]:
                continue
            title = f"Contexto sempre carregado: camada {key} perto ou acima do orçamento"
            if any(i["title"] == title and i["status"] == "open" for i in data["items"]):
                continue
            decisions.new_item(data, "manual", title, level="superego", detail=msg,
                               options=["A enxugar as fontes da camada", "B realocar orçamento entre camadas"],
                               source="tools/context_budget.py")
            added.append(title)
        if added:
            decisions.save(data, home)
    return added


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=os.environ.get("SYNC_MANIFEST"), help="default: <root>/psique/manifest.json")
    ap.add_argument("--root", help="folder holding the layer repos (default: $PSIQUE_ROOT, else the parent of this checkout)")
    ap.add_argument("--claude-home", default=os.path.expanduser("~/.claude"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--inbox", action="store_true", help="add one decision item per layer in the band or over")
    ap.add_argument("--repo", help="layer repo checkout: sizes of its always-loaded files (CI)")
    ap.add_argument("--base", help="with --repo: git ref to show the delta against")
    args = ap.parse_args()
    if args.repo:
        now = repo_sizes(args.repo)
        base = repo_sizes(args.repo, args.base) if args.base else {}
        total_now, total_base = sum(now.values()), sum(base.values())
        print(f"Always-loaded files of this layer: {total_now} bytes" + (f" ({total_now - total_base:+d} vs {args.base})" if args.base else ""))
        for f in sorted(set(now) | set(base)):
            a, b = base.get(f, 0), now.get(f, 0)
            if not args.base or a != b:
                print(f"- {f}: {b}" + (f" ({b - a:+d})" if args.base else ""))
        return 0
    rep = report(expand(args.manifest or roots.default_manifest(args.root)), expand(args.claude_home))
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print_report(rep)
    if args.inbox:
        for t in add_inbox_items(rep, expand(args.claude_home)):
            print(f"inbox: {t}")
    return 1 if rep["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
