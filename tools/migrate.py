#!/usr/bin/env python3
"""One-time migration from the old names to the new ones (pre-1.0 rename), driven by tools/renames.json.

  python -I tools/migrate.py [--root DIR | --manifest M] [--claude-home H]            # print the map and what is pending
  python -I tools/migrate.py ... --apply [--repos]                                     # rewrite what is pending

Without --apply nothing is written. --apply renames files and skill folders under the claude home and rewrites
@imports. Repository URLs in the manifest change only with --repos, and only after the repository exists under
the new name. Running it twice is a no-op. `deprecated()` is the one-line warning an old entry point prints while
it still works.
"""
import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import roots  # noqa: E402

MAP_FILE = Path(__file__).resolve().parent / "renames.json"
IMPORT = re.compile(r"^(@\S*?/)?([^/\s]+\.md)(\s*)$", re.M)


def load_map(path: Path = MAP_FILE) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {k: data.get(k, {}) for k in ("repos", "files", "skills")}
    out["removed_after"] = data.get("removed_after", "")
    return out


def deprecated(old: str, new: str, stream=None, removed_after: str = "") -> None:
    """The warning an old entry point prints; it keeps working for one minor release."""
    when = f" and goes away in {removed_after}" if removed_after else ""
    print(f"DEPRECATED: {old} is now {new}{when}. Run tools/migrate.py to update your setup.", file=stream or sys.stderr)


def repo_name(url: str) -> str:
    """Repository name of a GitHub URL (ssh or https), without owner or .git."""
    m = re.search(r"github\.com[:/][^/\s]+/([^/\s]+?)(?:\.git)?$", url)
    return m.group(1) if m else ""


def swap_repo(url: str, old: str, new: str) -> str:
    """Same URL with the repository name changed; the owner and the scheme stay."""
    if repo_name(url) != old:
        return url
    return re.sub(r"(github\.com[:/][^/\s]+/)" + re.escape(old) + r"((?:\.git)?)$", lambda m: m.group(1) + new + m.group(2), url)


def plan(manifest: dict, claude_home: Path, rename_map: dict) -> list[dict]:
    """What is pending, as [{kind, old, new, where}]."""
    out: list[dict] = []
    for layer in manifest.get("layers", []):
        new = rename_map["repos"].get(repo_name(layer.get("repo", "")))
        if new:
            out.append({"kind": "repo", "old": repo_name(layer["repo"]), "new": new, "where": layer.get("level", "")})
    for old, new in rename_map["files"].items():
        if (claude_home / old).exists() and not (claude_home / new).exists():
            out.append({"kind": "file", "old": old, "new": new, "where": str(claude_home)})
    for old, new in rename_map["skills"].items():
        if (claude_home / "skills" / old).is_dir() and not (claude_home / "skills" / new).exists():
            out.append({"kind": "skill", "old": old, "new": new, "where": str(claude_home / "skills")})
    return out


def rewrite_text(text: str, files: dict[str, str]) -> str:
    """Swap the file name in `@.../old.md` import lines."""
    def swap(m: re.Match) -> str:
        new = files.get(m.group(2))
        return f"{m.group(1) or ''}{new}{m.group(3)}" if new and m.group(1) else m.group(0)
    return IMPORT.sub(swap, text)


def apply(manifest_path: Path, claude_home: Path, rename_map: dict, repos: bool) -> list[str]:
    done: list[str] = []
    names = {Path(o).name: Path(n).name for o, n in rename_map["files"].items()}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for ch in plan(manifest, claude_home, rename_map):
        if ch["kind"] == "file":
            target = Path(ch["where"]) / ch["new"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(Path(ch["where"]) / ch["old"]), str(target))
            done.append(f"file {ch['old']} -> {ch['new']}")
        elif ch["kind"] == "skill":
            shutil.move(str(Path(ch["where"]) / ch["old"]), str(Path(ch["where"]) / ch["new"]))
            done.append(f"skill {ch['old']} -> {ch['new']}")
    for md in [claude_home / "CLAUDE.md", *claude_home.glob("global/*.md"), *claude_home.glob("rules/*.md")]:
        if md.is_file():
            text = md.read_text(encoding="utf-8")
            new_text = rewrite_text(text, names)
            if new_text != text:
                md.write_text(new_text, encoding="utf-8", newline="\n")
                done.append(f"imports in {md.name}")
    if repos:
        changed = False
        for layer in manifest.get("layers", []):
            for old, new in rename_map["repos"].items():
                swapped = swap_repo(layer.get("repo", ""), old, new)
                if swapped != layer.get("repo"):
                    layer["repo"] = swapped
                    changed = True
                    done.append(f"manifest repo {old} -> {new}")
        if changed:
            manifest_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return done


def print_map(rename_map: dict, stream=sys.stdout) -> None:
    for kind in ("repos", "files", "skills"):
        for old, new in rename_map[kind].items():
            print(f"{kind[:-1]:6} {old} -> {new}", file=stream)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Migrate an install from the old names to the new ones.")
    ap.add_argument("--root")
    ap.add_argument("--manifest")
    ap.add_argument("--claude-home", default=os.path.expanduser("~/.claude"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--repos", action="store_true", help="with --apply: also rewrite manifest repo URLs")
    args = ap.parse_args(argv)
    manifest = Path(os.path.expanduser(args.manifest or roots.default_manifest(args.root)))
    home = Path(os.path.expanduser(args.claude_home))
    rename_map = load_map()
    print("old -> new map:")
    print_map(rename_map)
    pending = plan(json.loads(manifest.read_text(encoding="utf-8")), home, rename_map) if manifest.is_file() else []
    print(f"pending: {len(pending)}")
    for ch in pending:
        print(f"  {ch['kind']} {ch['old']} -> {ch['new']} ({ch['where']})")
    if args.apply:
        for line in apply(manifest, home, rename_map, args.repos):
            print("applied:", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
