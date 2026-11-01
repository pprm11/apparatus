# Shared helpers for sync.sh, restore.sh, weekly.sh and harvest.sh (sourced, not run).

# memory_project_key DIR: original home key for a memory folder shortened by layers.py, else its basename.
memory_project_key() {
  if [ -f "$1/.project-key" ]; then
    tr -d '\r\n' < "$1/.project-key"
  else
    basename "$1"
  fi
}

# Locks are directories holding an owner file "<pid> <start epoch> <token>". The token (pid + random) is
# unique per acquisition, so a release only removes a lock that is still ours.
declare -A _LOCK_TOKEN=()

# lock_acquire DIR [MAX_AGE_MIN]: take the lock. A held lock is stale when its pid is dead or it is older
# than MAX_AGE_MIN (default 120). Only the holder of the short-lived guard DIR.reclaim may inspect and remove
# a stale lock, and it re-reads the owner under the guard, so two contenders can never both reclaim it;
# mkdir then decides the single winner.
lock_acquire() {
  local dir="$1" max="${2:-120}" pid="" start="" tok="" now stale=0 guard="$1.reclaim"
  if [ -d "$dir" ]; then
    find "$guard" -maxdepth 0 -mmin +5 -exec rm -rf {} + 2>/dev/null || true   # guard left by a crashed run
    if mkdir "$guard" 2>/dev/null; then
      if [ -f "$dir/owner" ]; then
        read -r pid start tok < "$dir/owner" || true
        now="$(date +%s)"
        if ! kill -0 "${pid:-0}" 2>/dev/null || [ $((now - ${start:-0})) -gt $((max * 60)) ]; then stale=1; fi
      elif [ -d "$dir" ] && [ -n "$(find "$dir" -maxdepth 0 -mmin +"$max" 2>/dev/null)" ]; then
        stale=1   # lock from an older script version (or half-written): stale only when old
      fi
      if [ "$stale" = 1 ]; then
        echo "removed stale lock $dir (pid ${pid:-?})"
        rm -rf "$dir"
      fi
      rmdir "$guard" 2>/dev/null || true
    fi
  fi
  mkdir "$dir" 2>/dev/null || return 1
  tok="$$-$RANDOM$RANDOM-$(date +%s)"
  _LOCK_TOKEN["$dir"]="$tok"
  echo "$$ $(date +%s) $tok" > "$dir/owner"
}

# lock_release DIR: remove the lock only if its owner file still holds our token.
lock_release() {
  local dir="$1" pid="" start="" tok="" moved
  if [ -f "$dir/owner" ] && [ -n "${_LOCK_TOKEN[$dir]:-}" ]; then
    read -r pid start tok < "$dir/owner" || true
    if [ "$tok" = "${_LOCK_TOKEN[$dir]}" ]; then
      moved="$dir.rel.$$.$RANDOM"
      if mv "$dir" "$moved" 2>/dev/null; then rm -rf "$moved"; fi
    fi
  fi
  unset '_LOCK_TOKEN[$dir]' 2>/dev/null || true
  return 0
}

# lock_wait DIR MAX_WAIT_S [MAX_AGE_MIN]: retry lock_acquire every 15 s.
lock_wait() {
  local dir="$1" waited=0 limit="$2" max="${3:-120}"
  until lock_acquire "$dir" "$max"; do
    if [ "$waited" -ge "$limit" ]; then return 1; fi
    sleep 15
    waited=$((waited + 15))
  done
}

# weekly_running REPO: true while the weekly pass edits memory/ (a lock older than 180 min is dead).
weekly_running() {
  local f="$1/.work/weekly.lock"
  [ -f "$f" ] || return 1
  find "$f" -maxdepth 0 -mmin +180 -delete 2>/dev/null || true
  [ -f "$f" ]
}

# codex_canary_due REPO: true unless the Codex canary already ran today.
codex_canary_due() {
  [ "$(cat "$1/.work/codex-canary.stamp" 2>/dev/null || true)" != "$(date +%F)" ]
}

# manifest_layer_path MANIFEST LEVEL: path of the first active layer with that level (forward slashes), or empty.
manifest_layer_path() {
  _manifest_layer_path "$@" | tr -d '\r'
}
_manifest_layer_path() {
  python -I - "$1" "$2" <<'PY'
import json, os, sys
for l in json.load(open(sys.argv[1], encoding="utf-8"))["layers"]:
    if l.get("active", True) and l["level"] == sys.argv[2]:
        print(os.path.normpath(os.path.expanduser(l["path"])).replace("\\", "/"))
        break
PY
}

# tilde_path PATH: "~/rest" when PATH is under $HOME (the form Claude Code permission rules use), else PATH.
tilde_path() {
  local p="$1" h="${HOME//\\//}"
  case "$p" in "$h"/*) echo "~/${p#"$h"/}" ;; *) echo "$p" ;; esac
}

# native_path PATH: the path as the host's native tools (python, powershell) read it. Git Bash and Cygwin
# translate /c/... with cygpath -m; elsewhere (WSL, Linux, macOS) the path is already native.
native_path() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi
}

# public_mirror TOOL_ROOT SOURCE: the public-mirror step of sync.sh. Off unless PUBLIC_MIRROR=1. The target folder
# comes from PUBLIC_MIRROR_DIR; with PUBLIC_MIRROR_REMOTE set it also publishes (one commit, no history, force
# push). tools/mirror_public.py runs the deny scan first and exits 2 on a hit, writing nothing. docs/public-mirror.md.
public_mirror() {
  [ "${PUBLIC_MIRROR:-0}" = 1 ] || return 0
  if [ -z "${PUBLIC_MIRROR_DIR:-}" ]; then echo "public mirror: PUBLIC_MIRROR_DIR is not set" >&2; return 1; fi
  local args=(--source "$2" --target "$PUBLIC_MIRROR_DIR")
  if [ -n "${PUBLIC_MIRROR_REMOTE:-}" ]; then args+=(--publish --remote "$PUBLIC_MIRROR_REMOTE"); fi
  python -I "$1/tools/mirror_public.py" "${args[@]}"
}
