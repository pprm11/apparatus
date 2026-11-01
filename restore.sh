#!/usr/bin/env bash
# Restore one layer repo into ~/.claude (overwrites same-name files, keeps others). Run once per layer, in
# manifest order (superego, ego, id); psique/restore.sh does that and then composes CLAUDE.md.
# Usage: ./restore.sh --from <layer repo path> [--claude-home ~/.claude]
set -euo pipefail
echo "== $(date '+%F %T') $0 $*"
shopt -s nullglob

DST="${CLAUDE_HOME:-$HOME/.claude}"
TOOLS="$(cd "$(dirname "$0")" && pwd)/tools"
# shellcheck source=lib.sh
. "$TOOLS/../lib.sh"
SRC=""
while [ $# -gt 0 ]; do
  case "$1" in
    --from) SRC="$2"; shift ;;
    --claude-home) DST="$2"; shift ;;
    *) echo "unknown argument $1" >&2; exit 1 ;;
  esac
  shift
done
[ -n "$SRC" ] && [ -d "$SRC" ] || { echo "usage: restore.sh --from <layer repo>" >&2; exit 1; }
# The superego layer lives in <apparatus>/superego; a path to the apparatus checkout still works.
[ ! -f "$SRC/layer.json" ] && [ -f "$SRC/superego/layer.json" ] && SRC="$SRC/superego"
mkdir -p "$DST/skills" "$DST/projects" "$DST/plugins" "$DST/rules"
git -C "$SRC" config core.safecrlf false 2>/dev/null || true

copy() { python -I "$TOOLS/mirror.py" "$1" "$2" --no-delete; }   # incremental, keeps files not in the repo

# Global files; settings.json only when the machine has none yet, so a restore never clobbers live settings.
for f in "$SRC"/global/*; do
  name="$(basename "$f")"
  if [ "$name" = "settings.json" ] && [ -e "$DST/settings.json" ]; then
    cp "$f" "$DST/settings.json.restored"
    echo "settings.json exists; restored copy saved as settings.json.restored"
  else
    cp "$f" "$DST/$name"
  fi
done
[ -d "$SRC/skills" ] && copy "$SRC/skills" "$DST/skills"
[ -d "$SRC/rules" ] && copy "$SRC/rules" "$DST/rules"
for d in "$SRC"/memory/*/; do
  proj="$(memory_project_key "$d")"
  mkdir -p "$DST/projects/$proj/memory"
  copy "$d" "$DST/projects/$proj/memory"
  rm -f "$DST/projects/$proj/memory/.project-key"
done
# Folders and single files named by layer.json (dirs, files), plus the decision inbox subset (merged).
python -I - "$SRC" "$DST" "$TOOLS" <<'PY'
import json, os, subprocess, sys
src, dst, tools = sys.argv[1:4]
cfg = json.load(open(os.path.join(src, "layer.json"), encoding="utf-8")) if os.path.isfile(os.path.join(src, "layer.json")) else {}
for d in cfg.get("dirs", []):
    s = os.path.join(src, d)
    if os.path.isdir(s):
        subprocess.run([sys.executable, "-I", os.path.join(tools, "mirror.py"), s, os.path.join(dst, d), "--no-delete"], check=True)
for f in cfg.get("files", []):
    s = os.path.join(src, f)
    if os.path.isfile(s):
        os.makedirs(os.path.dirname(os.path.join(dst, f)), exist_ok=True)
        import shutil; shutil.copy2(s, os.path.join(dst, f))
inbox = os.path.join(src, "decisions", "inbox.json")
if os.path.isfile(inbox):
    subprocess.run([sys.executable, "-I", os.path.join(tools, "decisions.py"), "--home", dst, "import", inbox], check=True)
PY
echo "Restored $SRC into $DST."
