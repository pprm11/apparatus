#!/usr/bin/env python3
"""Route the agent context in ~/.claude (source of truth) into the layer repos listed by the self manifest.

Levels: superego = general harness, ego = company context, id = personal. Each layer repo
has a layer.json saying what it owns; memories and skills are routed by the `level:` field of their
frontmatter (missing field = the manifest's default level, normally the active ego).

  python -I tools/layers.py plan   --manifest <root>/self/manifest.json [--claude-home ~/.claude]
  python -I tools/layers.py export --manifest M --level ego [--dry-run]     # write that layer's repo tree
  python -I tools/layers.py export --manifest M --all                       # every active layer
  python -I tools/layers.py unlabeled --manifest M                          # memories/skills without level:

manifest.json: {"default_level": "ego", "layers": [{"level": "superego", "path": "superego",
"repo": "git@github.com:me/superego.git", "active": true}, ...]}
layer.json (in each repo): {"level": "ego", "name": "acme", "globals": ["glossario-acme.md"],
"rules": ["projetos-acme.md"], "dirs": ["maps", "plans"], "files": ["decisions/config.json"]}
  globals: files at the root of ~/.claude copied to <repo>/global/
  rules:   files of ~/.claude/rules copied to <repo>/rules/
  dirs:    whole folders of ~/.claude mirrored to <repo>/<dir> (relative paths allowed: scripts/medicoes)
  files:   single files of ~/.claude copied to the same relative path
  inbox:   true on the one layer that keeps the live decision inbox (~/.claude/decisions/inbox.json)
  sealed:  paths of ~/.claude (folders or files, memories included) that never enter the repo in plain
           text; the export skips them and the repo's own tools/seal.sh encrypts them into sealed/
A memory or a skill (its SKILL.md) can also carry `sealed: true` in its frontmatter, top level or under
`metadata:`: the export withholds it under any project key, and keeps it out of the MEMORY.md index it
writes, so a repo move (which renames the key) cannot defeat the protection. Any `sealed:` value that is
not a clear no (false, no, off, 0, null, empty) counts as yes. The id repo's tools/seal.sh and pre-commit
honor the same flag.
Memories go to <repo>/memory/<project key>/<file> (a key over PROJECT_KEY_LIMIT characters is shortened to
<first 60 characters>-<10 hex of its sha256>, and the folder keeps the original key in .project-key), skills to <repo>/skills/<name>, the decision inbox to
<repo>/decisions/inbox.json of the layer with "inbox": true. Files the export did not
produce under global/, rules/, skills/, memory/ and the listed dirs are removed from the repo tree, so a
file whose level changed moves between repos on the next sync. The repo's own files (README, layer.json,
.gitignore, tools/, tests/ ...) are never touched.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mirror as mirror_mod  # noqa: E402
from ospaths import long_path as lp  # noqa: E402
import roots  # noqa: E402

LEVELS = ("superego", "persona", "collective", "ego", "id")
# `level:` sits at the top of the block or, in the usual memory format, indented under `metadata:`.
LEVEL_RE = re.compile(r"^[ \t]*level:[ \t]*([a-z]+)[ \t]*$", re.M)
SEALED_RE = re.compile(r"^[ \t]*sealed:(.*)$", re.M)
SEALED_NO = {"", "false", "no", "off", "0", "null", "~"}  # every other value is a yes: a leak guard fails closed
FRONT_END_RE = re.compile(r"\n---[ \t]*(?:\r?\n|$)")
FRONT_MAX = 64 * 1024  # a frontmatter longer than this is cut, so the flag must sit before that point
MANAGED = ("global", "rules", "skills", "memory", "decisions/inbox.json")
TOOLS = os.path.dirname(os.path.abspath(__file__))
PROJECT_KEY_LIMIT = 100  # a longer key (a scratch session without a folder) would push repo paths past Windows MAX_PATH
PROJECT_KEY_MARKER = ".project-key"  # in a shortened repo folder: the original key, which restore.sh reads back


def expand(path: str) -> str:
    return os.path.normpath(os.path.expanduser(path))


def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def frontmatter_block(path: str) -> str | None:
    """The first YAML block of a markdown file (between the opening and closing `---`), or None when the file
    has none. A UTF-8 BOM, blank lines before the block and CRLF are tolerated; a missing file or a folder is
    "no block"; any other OSError propagates so the caller decides which way to fail."""
    if os.path.isdir(lp(path)):
        return None
    try:
        with open(lp(path), encoding="utf-8-sig", errors="replace") as fh:
            head = fh.read(FRONT_MAX)
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None
    head = head.lstrip("\r\n")
    if not head.startswith("---"):
        return None
    m = FRONT_END_RE.search(head, 3)
    return head[3:m.start()] if m else head[3:]


def frontmatter_level(path: str) -> str | None:
    """`level:` inside the first YAML block of a markdown file, or None."""
    try:
        block = frontmatter_block(path)
    except OSError:
        return None
    m = LEVEL_RE.search(block) if block is not None else None
    if not m:
        return None
    return m.group(1) if m.group(1) in LEVELS else None


def frontmatter_sealed(path: str) -> bool:
    """True when the first YAML block carries a `sealed:` key (top level or under `metadata:`) whose value is
    not a clear no. Spelling variants (`True`, `yes`, quotes, a trailing comment) and an unreadable file all
    count as sealed: this guard fails closed."""
    try:
        block = frontmatter_block(path)
    except OSError:
        return True
    if block is None:
        return False
    for m in SEALED_RE.finditer(block):
        value = m.group(1).split("#", 1)[0].strip().strip("'\"").strip().lower()
        if value not in SEALED_NO:
            return True
    return False


def withheld(rel: str, path: str, sealed: list[str]) -> bool:
    """True when `path` (relative `rel` in ~/.claude) must not enter a repo in plain text: a path listed under
    `sealed` in layer.json, or a memory, SKILL.md or markdown file flagged `sealed: true`."""
    if is_sealed(rel, sealed):
        return True
    target = os.path.join(path, "SKILL.md") if os.path.isdir(lp(path)) else path
    return target.lower().endswith(".md") and frontmatter_sealed(target)


def load_manifest(path: str, root: str | None = None) -> dict:
    """Relative layer paths hang off `root` (default: the folder that holds the manifest's repo)."""
    man = read_json(path)
    man.setdefault("default_level", "ego")
    root = root or os.path.dirname(os.path.dirname(os.path.abspath(path)))
    for layer in man["layers"]:
        layer["path"] = roots.resolve_layer_path(layer["path"], root)
        nested = os.path.join(layer["path"], "superego")
        if (layer.get("level") == "superego" and not os.path.isfile(os.path.join(layer["path"], "layer.json"))
                and os.path.isfile(os.path.join(nested, "layer.json"))):
            layer["path"] = nested  # a manifest from before the layer moved under <apparatus>/superego keeps working
        layer.setdefault("active", True)
        cfg = os.path.join(layer["path"], "layer.json")
        layer["config"] = read_json(cfg) if os.path.isfile(cfg) else {}
    return man


def active_layers(man: dict) -> list[dict]:
    return [l for l in man["layers"] if l["active"]]


def sealed_paths(cfg: dict) -> list[str]:
    return [os.path.normcase(os.path.normpath(p)) for p in cfg.get("sealed", [])]


def is_sealed(rel: str, sealed: list[str]) -> bool:
    """True when `rel` (relative to ~/.claude) is one of the sealed paths or sits inside one."""
    r = os.path.normcase(os.path.normpath(rel))
    return any(r == s or r.startswith(s + os.sep) for s in sealed)


def is_readonly(layer: dict) -> bool:
    """A readonly layer (the shared collective) is pulled, never exported into, committed or pushed."""
    return layer.get("mode") == "readonly" or layer["config"].get("mode") == "readonly"


def writable_layers(man: dict) -> list[dict]:
    return [l for l in active_layers(man) if not is_readonly(l)]


def repo_root(path: str) -> str:
    """The git checkout that holds a layer: the layer folder itself, or the nearest parent with a .git (the
    superego layer lives in <apparatus>/superego)."""
    cur = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(path)
        cur = parent


def _git(repo: str, *args: str) -> str:
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else ""


def off_default_branch(repo: str) -> tuple[str, str] | None:
    """(current, default) when a readonly layer's checkout is not on its default branch (a task branch, a review
    worktree, a detached HEAD), else None. A readonly layer is only fast-forwarded, so such a checkout is skipped
    by `pull`; this never switches branches."""
    default = _git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").removeprefix("origin/") or "main"
    current = _git(repo, "symbolic-ref", "--short", "HEAD")
    return (current or "a detached HEAD", default) if current != default else None


def pull(man: dict, dry: bool = False) -> list[str]:
    """Bring each active readonly layer to its pinned `ref` (tag or SHA), or fast-forward it when no ref is set."""
    log: list[str] = []
    for layer in active_layers(man):
        if not is_readonly(layer):
            continue
        repo, ref = repo_root(layer["path"]), layer.get("ref")
        if not os.path.exists(os.path.join(repo, ".git")):
            log.append(f"[{layer['level']}] {repo} is not a git repo, skipped")
            continue
        has_remote = bool(subprocess.run(["git", "-C", repo, "remote"], capture_output=True, text=True).stdout.strip())
        if not has_remote:
            log.append(f"[{layer['level']}] no remote, nothing to pull")
            continue
        off = None if ref or dry else off_default_branch(repo)
        if off:
            msg = f"skipping pull of readonly layer {layer['level']} at {repo}: on {off[0]}, not {off[1]}"
            print(f"warning: {msg}", file=sys.stderr)
            log.append(f"[{layer['level']}] {msg}")
            continue
        cmds = [["git", "-C", repo, "fetch", "--tags", "--quiet"]]
        cmds.append(["git", "-C", repo, "checkout", "--quiet", ref] if ref else ["git", "-C", repo, "pull", "--ff-only", "--quiet"])
        for cmd in cmds:
            log.append(f"[{layer['level']}] {' '.join(cmd[3:])}")
            if not dry and subprocess.run(cmd, capture_output=True, text=True).returncode:
                raise SystemExit(f"pull failed for {repo}: {' '.join(cmd[3:])}")
    return log


def short_project_key(key: str, limit: int = PROJECT_KEY_LIMIT) -> str:
    """The repo folder name for a project key: the key itself up to `limit` characters, else a readable prefix
    plus a hash of the whole key, so it is stable and two long keys with the same start do not collide."""
    if len(key) <= limit:
        return key
    return f"{key[:60]}-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:10]}"


def level_of_memory(path: str, default: str) -> str:
    return frontmatter_level(path) or default


def level_of_skill(skill_dir: str, default: str) -> str:
    return frontmatter_level(os.path.join(skill_dir, "SKILL.md")) or default


def plan(man: dict, home: str) -> dict[str, list[tuple[str, str]]]:
    """{level: [(relative path in ~/.claude, relative path in the repo)]} for memories and skills."""
    default = man["default_level"]
    out: dict[str, list] = {l: [] for l in LEVELS}
    skills = os.path.join(home, "skills")
    marker = os.path.join(skills, ".company-skills.json")
    generated = set(read_json(marker).get("skills", [])) if os.path.isfile(marker) else set()
    for persona_marker in (os.path.join(home, ".persona-skills.json"), os.path.join(skills, ".persona-skills.json")):
        if os.path.isfile(persona_marker):
            receipt = read_json(persona_marker)
            import compose
            for name in receipt.get("skills", []):
                if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
                    raise SystemExit("invalid managed skill receipt")
                folder = os.path.join(skills, name)
                if os.path.lexists(folder) and (name not in receipt.get("hashes", {}) or compose.tree_hash(folder) != receipt["hashes"][name]):
                    raise SystemExit(f"managed skill changed or has no receipt: {name}")
            generated.update(receipt.get("skills", []))
    readonly_names = set()
    for layer in active_layers(man):
        if is_readonly(layer):
            root = os.path.join(layer["path"], "skills")
            if os.path.isdir(root):
                readonly_names.update(name for name in os.listdir(root) if os.path.isfile(os.path.join(root, name, "SKILL.md")))
        alias_path = layer["config"].get("skill_aliases")
        if alias_path and layer["level"] == "id":
            readonly_names.update(read_json(os.path.join(layer["path"], alias_path)).get("aliases", {}))
    if os.path.isdir(skills):
        for name in sorted(os.listdir(skills)):
            d = os.path.join(skills, name)
            if name == "synced" or name in generated or not os.path.isfile(os.path.join(d, "SKILL.md")):
                continue
            if name in readonly_names and not frontmatter_level(os.path.join(d, "SKILL.md")):
                raise SystemExit(f"unmanaged readonly skill collision: {name}")
            out[level_of_skill(d, default)].append((f"skills/{name}", f"skills/{name}"))
    projects = os.path.join(home, "projects")
    if os.path.isdir(projects):
        for key in sorted(os.listdir(projects)):
            mem = os.path.join(projects, key, "memory")
            if not os.path.isdir(lp(mem)):
                continue
            for name in sorted(os.listdir(lp(mem))):
                p = os.path.join(mem, name)
                if not name.endswith(".md") or not os.path.isfile(lp(p)):
                    continue
                lvl = default if name == "MEMORY.md" else level_of_memory(p, default)
                folder = short_project_key(key)
                out[lvl].append((f"projects/{key}/memory/{name}", f"memory/{folder}/{name}"))
                if name != "MEMORY.md" and lvl != default and os.path.isfile(lp(os.path.join(mem, "MEMORY.md"))):
                    idx = (f"projects/{key}/memory/MEMORY.md", f"memory/{folder}/MEMORY.md")
                    if idx not in out[lvl]:
                        out[lvl].append(idx)  # a layer that owns memories of this key also gets an index of them
    return out


def unlabeled(home: str) -> list[str]:
    res = []
    for name in sorted(os.listdir(os.path.join(home, "skills")) if os.path.isdir(os.path.join(home, "skills")) else []):
        s = os.path.join(home, "skills", name, "SKILL.md")
        if name != "synced" and os.path.isfile(s) and frontmatter_level(s) is None:
            res.append(f"skills/{name}")
    for key in sorted(os.listdir(os.path.join(home, "projects")) if os.path.isdir(os.path.join(home, "projects")) else []):
        mem = os.path.join(home, "projects", key, "memory")
        if not os.path.isdir(lp(mem)):
            continue
        for name in sorted(os.listdir(lp(mem))):
            if name.endswith(".md") and name != "MEMORY.md" and frontmatter_level(os.path.join(mem, name)) is None:
                res.append(f"projects/{key}/memory/{name}")
    return res


def copy_file(src: str, dst: str, dry: bool, log: list) -> None:
    if os.path.isfile(lp(dst)) and mirror_mod.same(src, dst):
        return
    log.append(f"copy {dst}")  # absolute: relpath() raises when cwd sits on another drive
    if not dry:
        os.makedirs(lp(os.path.dirname(dst)), exist_ok=True)
        mirror_mod.atomic_copy(src, dst)


INDEX_LINK_RE = re.compile(r"^[ \t]*[-*][ \t]+\[[^]]*\]\(([^)#]+\.md)\)")
INDEX_LINK_ANY = re.compile(INDEX_LINK_RE.pattern, re.M)  # the same, anywhere in a whole index text


def filter_index(src: str, level: str, default: str, home: str = "", sealed: list[str] | None = None) -> str:
    """MEMORY.md text with only the entries whose file this level owns (a file that is not there is kept).
    An entry whose file is sealed, by path or by flag, is dropped too: its title and hook are content."""
    mem = os.path.dirname(src)
    with open(lp(src), encoding="utf-8") as fh:
        lines = fh.read().splitlines(keepends=True)
    keep = []
    for ln in lines:
        m = INDEX_LINK_RE.match(ln)
        target = os.path.join(mem, m.group(1)) if m else ""
        if m and os.path.isfile(lp(target)):
            if level_of_memory(target, default) != level:
                continue
            if withheld(os.path.relpath(target, home) if home else "", target, sealed or []):
                continue
        keep.append(ln)
    return "".join(keep)


def write_index(src: str, dst: str, level: str, default: str, dry: bool, log: list, home: str = "",
                sealed: list[str] | None = None) -> bool:
    """Write the filtered index; False (and nothing written) when every entry the source listed was dropped."""
    text = filter_index(src, level, default, home, sealed)
    with open(lp(src), encoding="utf-8") as fh:
        had_entries = INDEX_LINK_ANY.search(fh.read()) is not None
    if had_entries and not INDEX_LINK_ANY.search(text):
        return False
    if os.path.isfile(dst):
        with open(dst, encoding="utf-8", newline="") as fh:
            if fh.read() == text:
                return True
    log.append(f"write {dst}")
    if not dry:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    return True


def copy_tree(src: str, dst: str, dry: bool, log: list, produced: set, repo: str, home: str = "",
              sealed: list[str] | None = None) -> None:
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in mirror_mod.DEFAULT_XD]
        if sealed:
            dirs[:] = [d for d in dirs if not is_sealed(os.path.relpath(os.path.join(root, d), home), sealed)]
        for f in files:
            s = os.path.join(root, f)
            rel_home = os.path.relpath(s, home) if home else ""
            if withheld(rel_home, s, sealed or []):
                log.append(f"withheld {rel_home or s} (sealed)")
                continue
            rel = os.path.relpath(s, src)
            d = os.path.join(dst, rel)
            produced.add(os.path.normcase(os.path.relpath(d, repo)))
            copy_file(s, d, dry, log)


def prune(repo: str, roots: list[str], produced: set, dry: bool, log: list) -> None:
    """Remove files under the managed roots that this export did not produce (and empty folders)."""
    for r in roots:
        base = os.path.join(repo, r)
        if os.path.isfile(base):
            if os.path.normcase(r) not in produced:
                log.append(f"remove {r}")
                if not dry:
                    os.remove(base)
            continue
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base, topdown=False):
            for f in files:
                p = os.path.join(root, f)
                rel = os.path.normcase(os.path.relpath(p, repo))
                if rel not in produced:
                    log.append(f"remove {os.path.relpath(p, repo)}")
                    if not dry:
                        os.remove(p)
            if not dry and not os.listdir(root):
                os.rmdir(root)


def write_key_marker(rel_src: str, rel_dst: str, repo: str, produced: set, dry: bool, log: list) -> None:
    """Keep the original project key in a shortened memory folder, so restore.sh can put the files back."""
    parts = rel_src.split("/")
    if parts[0] != "projects" or parts[2:3] != ["memory"] or os.path.normcase(rel_dst) not in produced:
        return
    key, folder = parts[1], rel_dst.split("/")[1]
    if key == folder:
        return
    marker = f"memory/{folder}/{PROJECT_KEY_MARKER}"
    if os.path.normcase(marker) in produced:
        return
    produced.add(os.path.normcase(marker))
    dst = os.path.join(repo, marker)
    if os.path.isfile(dst):
        with open(dst, encoding="utf-8", newline="") as fh:
            if fh.read() == key + "\n":
                return
    log.append(f"write {dst}")
    if not dry:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8", newline="") as fh:
            fh.write(key + "\n")


def export(man: dict, home: str, level: str, dry: bool = False) -> list[str]:
    layers = [l for l in writable_layers(man) if l["level"] == level]
    if not layers:
        raise SystemExit(f"no active writable layer with level {level} in the manifest")
    layer = layers[0]
    repo, cfg = layer["path"], layer["config"]
    if not os.path.isdir(repo):
        raise SystemExit(f"layer repo {repo} is missing")
    routes = plan(man, home)
    log: list[str] = []
    produced: set[str] = set()
    sealed = sealed_paths(cfg)
    for f in cfg.get("globals", []):
        s = os.path.join(home, f)
        if os.path.isfile(s):
            d = os.path.join(repo, "global", f)
            produced.add(os.path.normcase(os.path.relpath(d, repo)))
            copy_file(s, d, dry, log)
    for f in cfg.get("rules", []):
        s = os.path.join(home, "rules", f)
        if os.path.isfile(s):
            d = os.path.join(repo, "rules", f)
            produced.add(os.path.normcase(os.path.relpath(d, repo)))
            copy_file(s, d, dry, log)
    for rel_src, rel_dst in routes[level]:
        s, d = os.path.join(home, rel_src), os.path.join(repo, rel_dst)
        if withheld(rel_src, s, sealed):
            log.append(f"withheld {rel_src} (sealed)")  # only its .age copy may enter the repo (tools/seal.sh)
            continue
        if os.path.isdir(s):
            copy_tree(s, d, dry, log, produced, repo, home, sealed)
        elif rel_src.endswith("/memory/MEMORY.md"):
            if write_index(s, d, level, man["default_level"], dry, log, home, sealed):
                produced.add(os.path.normcase(rel_dst))
            else:
                log.append(f"withheld {rel_src} (every entry of this level is sealed)")
        else:
            produced.add(os.path.normcase(rel_dst))
            copy_file(s, d, dry, log)
        write_key_marker(rel_src, rel_dst, repo, produced, dry, log)
    roots = list(MANAGED)
    for d in cfg.get("dirs", []):
        s = os.path.join(home, d)
        if is_sealed(d, sealed):
            continue
        roots.append(d)
        if os.path.isdir(s):
            copy_tree(s, os.path.join(repo, d), dry, log, produced, repo, home, sealed)
    for f in cfg.get("files", []):
        s = os.path.join(home, f)
        if os.path.isfile(s) and not is_sealed(f, sealed):
            d = os.path.join(repo, f)
            produced.add(os.path.normcase(f))
            copy_file(s, d, dry, log)
    # Decision inbox: the whole live store goes to the layer whose layer.json says "inbox": true (the id
    # layer; decisions are the user's). Other layers never carry it; prune drops an old copy.
    inbox = os.path.join(home, "decisions", "inbox.json")
    if cfg.get("inbox") and os.path.isfile(inbox):
        d = os.path.join(repo, "decisions", "inbox.json")
        produced.add(os.path.normcase("decisions/inbox.json"))
        copy_file(inbox, d, dry, log)
    # Generated readonly skills are not exported; preserve any preexisting namesake
    # rather than pruning data whose ownership cannot be inferred from this home.
    marker = os.path.join(home, "skills", ".company-skills.json")
    generated = set(read_json(marker).get("skills", [])) if os.path.isfile(marker) else set()
    for persona_marker in (os.path.join(home, ".persona-skills.json"), os.path.join(home, "skills", ".persona-skills.json")):
        if os.path.isfile(persona_marker):
            generated.update(read_json(persona_marker).get("skills", []))
    for name in generated:
        existing = os.path.join(repo, "skills", name)
        for root, _, files in os.walk(existing):
            for filename in files:
                produced.add(os.path.normcase(os.path.relpath(os.path.join(root, filename), repo)))
    # An incomplete skill folder may contain private reference material. Its
    # owner is unknown, so export must not prune it.
    skills_root = os.path.join(repo, "skills")
    if os.path.isdir(skills_root):
        for name in os.listdir(skills_root):
            folder = os.path.join(skills_root, name)
            if os.path.isdir(folder) and not os.path.isfile(os.path.join(folder, "SKILL.md")):
                for root, _, files in os.walk(folder):
                    for filename in files:
                        produced.add(os.path.normcase(os.path.relpath(os.path.join(root, filename), repo)))
    prune(repo, roots, produced, dry, log)
    return log


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "export", "unlabeled", "pull"])
    ap.add_argument("--manifest", help="default: <root>/self/manifest.json")
    ap.add_argument("--root", help="folder holding the layer repos (default: $PSIQUE_ROOT, else the parent of this checkout)")
    ap.add_argument("--claude-home", default=os.path.expanduser("~/.claude"))
    ap.add_argument("--level", choices=LEVELS)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    home = expand(args.claude_home)
    man = load_manifest(expand(args.manifest or roots.default_manifest(args.root)))
    if args.cmd == "plan":
        for lvl, items in plan(man, home).items():
            for src, dst in items:
                print(f"{lvl}\t{src}\t{dst}")
        return 0
    if args.cmd == "pull":
        for line in pull(man, args.dry_run):
            print(line)
        return 0
    if args.cmd == "unlabeled":
        for p in unlabeled(home):
            print(p)
        return 0
    levels = [l["level"] for l in writable_layers(man)] if args.all else [args.level]
    if not levels or levels == [None]:
        raise SystemExit("export needs --level or --all")
    for lvl in levels:
        for line in export(man, home, lvl, args.dry_run):
            print(f"[{lvl}] {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
