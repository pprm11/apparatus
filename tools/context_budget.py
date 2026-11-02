#!/usr/bin/env python3
"""Byte budget of the always-loaded context, per layer (the ubiquitous "AGENTS.md never fills up" rule).

Every file that reaches the Codex AGENTS.md (and the Claude CLAUDE.md imports) belongs to one layer: the
`.md` globals and the `rules` of each layer.json, the harness adapter (budget key "adapter", the largest
harness/*.md), and the root CLAUDE.md (key "root"). self/manifest.json carries the budgets:

    "budgets": {"superego": 12500, "collective": 1500, "ego": 6800, "id": 6600, "adapter": 2700, "root": 900}

They must sum to under the Codex limit (32,768) with headroom. A layer over its budget is a problem (the
render refuses to write, CI fails). Over BAND (90%) is the gate that keeps the file from ever filling up:
the Claude write hook (scripts/hook-context-budget.py) refuses the edit that crosses it, sync.sh holds the
layer's always-loaded files back from the commit and opens one decision item with the cut candidates
(--inbox), and the layer repo's CI fails (--repo --budget). With the budgets summing to at most 95% of the
limit, 90% of them is 27,900 bytes: under the 28,672 warning line of render_harness.py by construction.
A loaded file no layer owns is a problem too: nothing is always-loaded without a budget.

  python -I tools/context_budget.py [--manifest M] [--claude-home H] [--json] [--inbox] [--list-band]
  python -I tools/context_budget.py --repo DIR [--base REF] [--budget N]   # one layer repo (CI): sizes of
                                   # global/*.md and rules/*.md in the checkout, delta against REF; with
                                   # --budget, exit 1 when the layer is over the band of that budget
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python -I drops the script dir
import roots  # noqa: E402

LIMIT = 32768
BAND = 0.90
HEADROOM = 0.05  # the budgets together leave at least this share of the limit free
CANDIDATES = 5  # cut candidates listed per layer in the decision item
MIN_BULLET = 200  # a list item this long counts as a cut candidate of its own
HEADING = re.compile(r"^#{1,3} +(.+?)\s*$")
BULLET = re.compile(r"^- \*\*(.+?)\*\*")


def nbytes(path: str) -> int:
    with open(path, "rb") as fh:
        return len(fh.read().replace(b"\r\n", b"\n"))


def expand(path: str) -> str:
    return os.path.normpath(os.path.expanduser(path))


def rel(path: str, home: str) -> str:
    return os.path.relpath(path, home).replace(os.sep, "/")


def band_limit(budget: int) -> int:
    return int(budget * BAND)


def layer_dir(path: str) -> str:
    """Folder holding a layer's layer.json: the path itself, or its nested superego/ (the superego layer lives
    under <apparatus>/superego since the pre-1.0 rename; an older manifest still points at the repo root)."""
    nested = os.path.join(path, "superego")
    if not os.path.isfile(os.path.join(path, "layer.json")) and os.path.isfile(os.path.join(nested, "layer.json")):
        return nested
    return path


def layer_files(man: dict, home: str) -> dict[str, list[str]]:
    """level -> always-loaded paths each active layer.json claims (globals .md and rules), existing or not."""
    out: dict[str, list[str]] = {}
    for l in man["layers"]:
        if not l.get("active", True):
            continue
        cfgp = os.path.join(layer_dir(expand(l["path"])), "layer.json")
        cfg = json.load(open(cfgp, encoding="utf-8")) if os.path.isfile(cfgp) else {}
        files = [os.path.join(home, g) for g in cfg.get("globals", []) if g.endswith(".md")]
        files += [os.path.join(home, "rules", r) for r in cfg.get("rules", [])]
        out[l["level"]] = files
    return out


def report(manifest_path: str, home: str) -> dict:
    man = json.load(open(manifest_path, encoding="utf-8"))
    budgets = man.get("budgets", {})
    layers = {}
    owned: set[str] = set()
    for level, claimed in layer_files(man, home).items():
        files = [p for p in claimed if os.path.isfile(p)]
        owned.update(os.path.normcase(f) for f in files)
        layers[level] = {"files": {rel(f, home): nbytes(f) for f in files}}
    adapters = sorted(glob.glob(os.path.join(home, "harness", "*.md")))
    layers["adapter"] = {"files": {rel(p, home): nbytes(p) for p in adapters}}
    root = os.path.join(home, "CLAUDE.md")
    layers["root"] = {"files": {"CLAUDE.md": nbytes(root)} if os.path.isfile(root) else {}}
    owned.update(os.path.normcase(p) for p in (*adapters, root))
    problems, warnings = [], []
    for key, info in layers.items():
        # The harnesses never load two adapters at once: the budget covers the largest one.
        total = max(info["files"].values(), default=0) if key == "adapter" else sum(info["files"].values())
        budget = budgets.get(key)
        info.update({"bytes": total, "budget": budget})
        if budget is None:
            if total:
                problems.append(f"{key}: {total} bytes loaded and no budget in the manifest")
            continue
        info["share"] = round(total / budget, 3) if budget else None
        if total > budget:
            problems.append(f"{key}: {total} bytes, over its budget of {budget} (trim {total - budget})")
        elif total > band_limit(budget):
            warnings.append(f"{key}: {total} bytes, {total * 100 // budget}% of its budget of {budget}")
    unowned = [rel(p, home) for p in sorted(glob.glob(os.path.join(home, "rules", "*.md")))
               if os.path.normcase(p) not in owned]
    for p in unowned:
        problems.append(f"{p}: always loaded but no layer.json lists it (no budget)")
    total_budget = sum(v for v in budgets.values() if isinstance(v, int))
    if budgets and total_budget > LIMIT * (1 - HEADROOM):
        problems.append(f"budgets sum to {total_budget}, over {int(LIMIT * (1 - HEADROOM))} (limit {LIMIT} minus headroom)")
    return {"layers": layers, "budgets": budgets, "limit": LIMIT, "loaded": sum(l["bytes"] for l in layers.values()),
            "problems": problems, "warnings": warnings, "unowned": unowned}


def band_layers(rep: dict) -> list[str]:
    """Budget keys in the band or over it (the gate of sync.sh and the hook), in report order."""
    flagged = {msg.split(":")[0] for msg in rep["problems"] + rep["warnings"]}
    return [key for key, info in rep["layers"].items() if key in flagged and info.get("budget")]


def candidates(files: dict[str, int], home: str, n: int = CANDIDATES) -> list[tuple[str, int]]:
    """The n largest cut candidates among the layer's files: a heading section, or a bold list item of
    MIN_BULLET bytes or more, labeled `file § title` with its bytes (what a trim would move to a skill).
    Units overlap on purpose: a section and its longest bullets are each something a trim could move whole.
    Text before the first heading is the `preamble`, fenced code is never a heading or a bullet, and a file
    with no unit at all is one candidate by itself."""
    units: list[tuple[str, int]] = []
    for relp in files:
        path = os.path.join(home, relp)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        found: list[tuple[str, int]] = []
        title, buf, fenced, headings = "preamble", [], False, 0
        for line in lines + ["# end"]:  # the sentinel closes the last section
            if line.startswith("```"):
                fenced = not fenced
                buf.append(line)
                continue
            m = None if fenced else HEADING.match(line)
            if m:
                body = "\n".join(buf).strip()
                if body and (headings or line != "# end"):  # a file with no heading is one unit, below
                    found.append((f"{relp} § {title}", len(body.encode("utf-8"))))
                title, buf, headings = m.group(1), [], headings + 1
                continue
            buf.append(line)
            b = None if fenced else BULLET.match(line)
            if b and len(line.encode("utf-8")) >= MIN_BULLET:
                found.append((f"{relp} § {b.group(1)}", len(line.encode("utf-8"))))
        units += found or [(relp, files[relp])]
    return sorted(units, key=lambda u: -u[1])[:n]


def check_write(manifest_path: str, home: str, path: str, new_bytes: int) -> str | None:
    """Message when writing `new_bytes` to `path` would take its layer over the band, else None. A write that
    shrinks the file always passes. Creating a rules/*.md that no layer.json lists is refused (it would be
    always loaded with no budget); an existing unlisted rule is left to `report`, which flags it, so the edit
    that fixes it is never blocked."""
    man = json.load(open(manifest_path, encoding="utf-8"))
    rep = report(manifest_path, home)
    relp = rel(path, home)
    key = next((lvl for lvl, files in layer_files(man, home).items() if relp in {rel(f, home) for f in files}), None)
    if key is None and relp.startswith("harness/") and relp.endswith(".md"):
        key = "adapter"
    elif key is None and relp == "CLAUDE.md":
        key = "root"
    if key is None:
        if relp.startswith("rules/") and relp.count("/") == 1 and relp.endswith(".md") and not os.path.isfile(path):
            return f"{relp}: a new rule is always loaded but no layer.json lists it; add it to a layer's rules (and its budget) first"
        return None
    info = rep["layers"].get(key) or {"files": {}, "bytes": 0, "budget": None}
    old = info["files"].get(relp, 0)
    if new_bytes <= old or not info.get("budget"):
        return None
    others = [n for f, n in info["files"].items() if f != relp]
    total = max([new_bytes, *others]) if key == "adapter" else info["bytes"] - old + new_bytes
    limit = band_limit(info["budget"])
    if total <= limit:
        return None
    return (f"{relp}: the {key} layer would reach {total} bytes, over {limit} ({int(BAND * 100)}% of its budget of "
            f"{info['budget']}); room left {max(limit - info['bytes'], 0)} bytes. Keep the rule to one line here and "
            f"move the detail to a skill (always-loaded text has a budget)")


def listed_in_layer_json(text: str | None) -> list[str] | None:
    """Repo paths of the always-loaded files a layer.json lists (globals .md under global/, rules under rules/)."""
    if text is None:
        return None
    cfg = json.loads(text)
    return [f"global/{g}" for g in cfg.get("globals", []) if g.endswith(".md")] + [f"rules/{r}" for r in cfg.get("rules", [])]


def repo_sizes(repo: str, ref: str | None = None) -> dict[str, int]:
    """Bytes of the always-loaded files of a layer repo checkout, or at a git ref: the ones its layer.json lists
    (at the repo root or nested under superego/), or every global/*.md and rules/*.md when there is no layer.json."""
    out: dict[str, int] = {}
    if ref is None:
        sub = os.path.relpath(layer_dir(repo), repo).replace(os.sep, "/")
        prefix = "" if sub == "." else sub + "/"
        cfgp = os.path.join(repo, prefix, "layer.json")
        listed = listed_in_layer_json(open(cfgp, encoding="utf-8").read() if os.path.isfile(cfgp) else None)
        if listed is not None:
            return {prefix + name: nbytes(os.path.join(repo, prefix, name)) for name in listed
                    if os.path.isfile(os.path.join(repo, prefix, name))}
        for pat in ("global/*.md", "rules/*.md"):
            for p in sorted(glob.glob(os.path.join(repo, pat))):
                out[os.path.relpath(p, repo).replace(os.sep, "/")] = nbytes(p)
        return out
    listed = None
    for prefix in ("", "superego/"):
        cfg = subprocess.run(["git", "-C", repo, "show", f"{ref}:{prefix}layer.json"], capture_output=True)
        if cfg.returncode == 0:
            listed = [prefix + name for name in listed_in_layer_json(cfg.stdout.decode("utf-8"))]
            break
    if listed is None:
        ls = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--name-only", ref, "global", "rules"],
                            capture_output=True, text=True, encoding="utf-8")
        listed = [name for name in ls.stdout.split() if name.endswith(".md")]
    for name in listed:
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
    """One open inbox item per layer in the band or over budget, with its cut candidates (sync.sh calls this)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import decisions  # noqa: E402

    added = []
    with decisions.locked(home):
        data = decisions.load(home)
        for msg in rep["problems"] + rep["warnings"]:
            key = msg.split(":")[0]
            if key not in rep["layers"]:
                continue
            title = f"Always-loaded context: layer {key} near or over budget"
            if any(i["title"] == title and i["status"] == "open" for i in data["items"]):
                continue
            files = rep["layers"][key]["files"]
            if key == "adapter" and files:  # only the largest adapter counts toward the budget
                largest = max(files, key=files.get)
                files = {largest: files[largest]}
            cuts = candidates(files, home)
            detail = msg + ". Cut candidates (move to a skill, keep a one-line pointer): " + "; ".join(
                f"{label} ({n} bytes)" for label, n in cuts)
            decisions.new_item(data, "manual", title, level="superego", detail=detail,
                               options=["A move the candidates to a skill", "B reallocate budget between layers (self manifest)"],
                               source="tools/context_budget.py")
            added.append(title)
        if added:
            decisions.save(data, home)
    return added


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=os.environ.get("SYNC_MANIFEST"), help="default: <root>/self/manifest.json")
    ap.add_argument("--root", help="folder holding the layer repos (default: $PSIQUE_ROOT, else the parent of this checkout)")
    ap.add_argument("--claude-home", default=os.path.expanduser("~/.claude"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--inbox", action="store_true", help="add one decision item per layer in the band or over")
    ap.add_argument("--list-band", action="store_true", help="print only the budget keys in the band or over, one per line")
    ap.add_argument("--repo", help="layer repo checkout: sizes of its always-loaded files (CI)")
    ap.add_argument("--base", help="with --repo: git ref to show the delta against")
    ap.add_argument("--budget", type=int, help="with --repo: the layer's budget from the self manifest; exit 1 over the band")
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
        if args.budget and total_now > band_limit(args.budget):
            # The gate stops growth: a change that leaves a layer still in the band, or trims it, passes.
            grew = total_now > total_base if args.base else True
            print(f"over the band: {total_now} bytes is more than {band_limit(args.budget)} ({int(BAND * 100)}% of the "
                  f"budget of {args.budget})" + ("" if grew else f", but not growing vs {args.base}: passes")
                  + "; move detail to a skill, keep the rule to one line")
            return 1 if grew else 0
        return 0
    rep = report(expand(args.manifest or roots.default_manifest(args.root)), expand(args.claude_home))
    if args.list_band:
        for key in band_layers(rep):
            print(key)
        return 0
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
