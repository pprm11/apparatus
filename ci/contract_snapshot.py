#!/usr/bin/env python3
"""Build and compare the snapshot of superego's public contract (docs/contract.md is the prose).

  python -I ci/contract_snapshot.py            # print the live contract as JSON
  python -I ci/contract_snapshot.py --write    # rewrite ci/contract.json from the live tree (additive change)
  python -I ci/contract_snapshot.py --fresh    # exit 1 when the live tree has items the snapshot lacks

tests/test_contract.py fails when ci/contract.json lists something the live tree no longer has. That is the
breaking-change detector: removing or renaming an entry needs a major release (GOVERNANCE.md). Adding is
free; --fresh is the release checklist step that keeps the snapshot and the docs complete.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "ci" / "contract.json"
TOOLS = ["onboard", "layers", "compose", "context_budget", "render_harness", "privacy", "bootstrap", "doctor", "roots", "migrate"]
FLAG = re.compile(r"^\s{1,4}(-[-A-Za-z0-9]+(?:, -[-A-Za-z0-9]+)*)", re.M)
CHOICES = re.compile(r"\{([A-Za-z0-9_,.-]+)\}(?:\s+\.\.\.)?\s*$")  # positional list closes the usage line
# Keys other layers read from each manifest layer entry (documented in tools/layers.py).
MANIFEST_LAYER_KEYS = ["level", "path", "repo", "active", "mode", "ref"]
THIRD_PARTY_SKILLS = {"neon", "neon-postgres"}


def help_text(tool: str, *sub: str) -> str:
    cmd = [sys.executable, "-I", str(ROOT / "tools" / f"{tool}.py"), *sub, "--help"]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=60)
    if res.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} exited {res.returncode}: {res.stderr[-300:]}")
    return res.stdout


def flags_of(text: str) -> list[str]:
    out: list[str] = []
    for m in FLAG.finditer(text):
        for f in m.group(1).split(", "):
            if f not in ("-h", "--help") and f not in out:
                out.append(f)
    return sorted(out)


def cli() -> dict:
    res: dict = {}
    for tool in TOOLS:
        text = help_text(tool)
        entry: dict = {"flags": flags_of(text)}
        usage = text.split("\n\n", 1)[0]
        found = CHOICES.search(usage)
        if found:
            subs = found.group(1).split(",")
            try:  # a flag a sub-command only inherits from the top level is not its own
                cmds = {s: flags_of(help_text(tool, s)) for s in subs}
                entry["commands"] = {s: [f for f in fl if f not in entry["flags"]] for s, fl in cmds.items()}
            except RuntimeError:  # plain positional choices, not argparse subparsers
                entry["commands"] = {s: [] for s in subs}
        res[tool] = entry
    return res


def ls(pattern: str) -> list[str]:
    return sorted(p.relative_to(ROOT).as_posix() for p in ROOT.glob(pattern) if p.is_file())


def live() -> dict:
    layer = json.loads((ROOT / "layer.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "templates/psique/manifest.json").read_text(encoding="utf-8"))
    skills = sorted(p.parent.name for p in ROOT.glob("skills/*/SKILL.md") if p.parent.name not in THIRD_PARTY_SKILLS)
    # Imported late: repo_gates holds the one list of layer.json keys.
    sys.path.insert(0, str(ROOT / "ci"))
    import repo_gates  # noqa: PLC0415
    return {
        "schema_version": 1,
        "layer_json_keys": sorted(repo_gates.LAYER_KEYS),
        "manifest_keys": sorted(manifest),
        "manifest_layer_keys": MANIFEST_LAYER_KEYS,
        "context_budget_keys": ["adapter", "collective", "ego", "id", "root", "superego"],
        "cli": cli(),
        "template_files": sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "templates").rglob("*") if p.is_file()),
        "read_paths": sorted(set(
            ["layer.json", "ci/privacy-terms.json", "harness/skills.json", "harness/claude.md", "harness/codex.md"]
            + [f"global/{n}" for n in layer["globals"]]
            + [f"rules/{n}" for n in layer["rules"]]
            + layer["files"] + [f"tools/{t}.py" for t in TOOLS])),
        "rule_ids": sorted(layer["globals"] + layer["rules"]),
        "skills": skills,
    }


def contains(snap, cur, path: str = "") -> list[str]:
    """Everything in snap that cur lacks; lists compare as sets, dicts key by key."""
    miss: list[str] = []
    if isinstance(snap, dict):
        for k, v in snap.items():
            if not isinstance(cur, dict) or k not in cur:
                miss.append(f"{path}/{k}")
            else:
                miss += contains(v, cur[k], f"{path}/{k}")
    elif isinstance(snap, list):
        have = set(cur) if isinstance(cur, list) else set()
        miss += [f"{path}: {x}" for x in snap if x not in have]
    return miss


def main() -> int:
    now = live()
    if "--write" in sys.argv:
        SNAPSHOT.write_text(json.dumps(now, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        return 0
    if "--fresh" in sys.argv:
        snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        new = contains(now, snap)
        print("\n".join(new) or "snapshot is complete")
        return 1 if new else 0
    print(json.dumps(now, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
