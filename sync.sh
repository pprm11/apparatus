#!/usr/bin/env bash
# Route the agent context in ~/.claude (source of truth) into the layer repos of the self manifest
# (superego, ego-<company>, id; tools/layers.py), then render it for Codex (tools/render_harness.py).
# Usage: ./sync.sh [--manifest <root>/self/manifest.json]            -> copy only
#        ./sync.sh --push [--manifest M]  -> copy, commit (up to 3 Conventional Commits) and push each layer
# Env: PUBLIC_MIRROR=1 also builds (and with PUBLIC_MIRROR_REMOTE publishes) the public mirror, docs/public-mirror.md.
# Exit codes: 0 ok or skipped (lock held, weekly running), 1 aborted by a safety check or failed, 75 skipped
# when the caller sets SYNC_REQUIRE=1 (weekly.sh does).
set -euo pipefail
# bash 4+ (mapfile, ${var//}); macOS ships 3.2: brew install bash. Same scripts on Linux, macOS and Git Bash.
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then echo "bash 4 or newer is required (macOS: brew install bash)" >&2; exit 1; fi
echo "== $(date '+%F %T') $0 $*"

SRC="${CLAUDE_HOME:-$HOME/.claude}"
DST="$(cd "$(dirname "$0")" && pwd)"
. "$DST/lib.sh"
PUSH=0
MANIFEST="${SYNC_MANIFEST:-$(default_manifest "${PSIQUE_ROOT:-$(dirname "$DST")}")}"
while [ $# -gt 0 ]; do
  case "$1" in
    --push) PUSH=1 ;;
    --manifest) MANIFEST="$2"; shift ;;
    *) echo "unknown argument $1" >&2; exit 1 ;;
  esac
  shift
done
[ -f "$MANIFEST" ] || { echo "ABORT: manifest $MANIFEST is missing" >&2; exit 1; }
# Active, writable layer repo paths, in manifest order (superego first). A readonly layer (the shared
# collective) is only pulled, below; it is never exported into, committed or pushed from here.
mapfile -t LAYERS < <(python -I - "$MANIFEST" <<'PY2'
import json, os, sys
for l in json.load(open(sys.argv[1], encoding="utf-8"))["layers"]:
    if l.get("active", True) and l.get("mode") != "readonly": print(l["level"] + "	" + os.path.normpath(os.path.expanduser(l["path"])).replace("\\", "/"))
PY2
)
cr=$'\r'; LAYERS=("${LAYERS[@]//$cr/}")   # python prints CRLF on Windows
layer_path() { local l; for l in "${LAYERS[@]}"; do [ "${l%%$'	'*}" = "$1" ] && { echo "${l#*$'	'}"; return; }; done; }
# layer_path returns 1 when the level is absent; under set -e a bare "$(...)" assignment would then end the
# script in silence, so the miss is caught here and reported.
EGO="$(layer_path ego || true)"
[ -n "$EGO" ] || echo "warning: no active ego layer in $MANIFEST"

skip() { echo "$1, sync skipped"; if [ -n "${SYNC_REQUIRE:-}" ]; then exit 75; fi; exit 0; }
abort() { echo "ABORT: $1" >&2; exit 1; }

# weekly.sh holds .sync.lock for its whole run and tells us so with SYNC_LOCK_HELD=1.
LOCK="$DST/.sync.lock"
if [ -z "${SYNC_LOCK_HELD:-}" ]; then
  # weekly.sh edits memory/ in this repo; skip this run instead of overwriting it.
  if weekly_running "$DST"; then skip "weekly pass running"; fi
  if ! lock_acquire "$LOCK" 120; then skip "another sync running"; fi
  trap 'lock_release "$LOCK"' EXIT
fi

# Safety net: an unmounted or half-restored ~/.claude must never be mirrored over the backup.
[ -f "$SRC/CLAUDE.md" ] || abort "$SRC/CLAUDE.md is missing; nothing was changed"
nmem="$(find "$SRC/projects" -mindepth 3 -maxdepth 3 -path '*/memory/*.md' 2>/dev/null | wc -l)"
[ "$nmem" -ge "${SYNC_MIN_MEMORIES:-20}" ] || abort "only $nmem memory files under $SRC/projects (need ${SYNC_MIN_MEMORIES:-20}); nothing was changed"

# Expected sources: if the backup already holds files in one of these and ~/.claude has it missing or
# empty, ~/.claude is broken (wrong profile, half restore). Abort before any destination is touched.
has_files() { [ -d "$1" ] && [ -n "$(ls -A "$1" 2>/dev/null)" ]; }
for l in "${LAYERS[@]}"; do
  lp="${l#*$'	'}"
  for d in skills rules harness; do
    if has_files "$lp/$d" && ! has_files "$SRC/$d"; then
      abort "$SRC/$d is missing or empty but $lp has $d/; nothing was changed"
    fi
  done
  for d in "$lp"/memory/*/; do
    [ -d "$d" ] || continue
    proj="$(memory_project_key "$d")"
    if has_files "$d" && ! has_files "$SRC/projects/$proj/memory"; then
      abort "$SRC/projects/$proj/memory is missing or empty but $lp has it; nothing was changed"
    fi
  done
done

# The checkout this script runs from is the live one: lock it to its default branch (see tools/branch_lock.py).
python -I "$DST/tools/branch_lock.py" install "$DST" || echo "branch lock not installed for $DST (see message above)"

# Pull the readonly layers (pinned `ref`, or fast-forward) before routing; a failed pull aborts the sync.
python -I "$DST/tools/layers.py" pull --manifest "$MANIFEST" || abort "pull of a readonly layer failed"
# Refresh only generated skills after pull; do not regenerate the active rule imports.
if python -I - "$MANIFEST" <<'PY2'
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    layers = json.load(fh).get("layers", [])
sys.exit(0 if any(l.get("level") == "persona" and l.get("active", True) for l in layers) else 1)
PY2
then
  if ! python -I "$DST/tools/compose.py" --manifest "$MANIFEST" --claude-home "$SRC" --skills-only; then
    # The failure blocks export. Record one generic item without copying skill contents into the inbox.
    python -I - "$DST/tools" "$SRC" <<'PY2' || echo "could not record persona refresh decision" >&2
import sys
sys.path.insert(0, sys.argv[1])
import decisions
home = sys.argv[2]
title = "Persona skill refresh blocked"
with decisions.locked(home):
    data = decisions.load(home)
    if not any(item.get("title") == title and item.get("status") == "open" for item in data["items"]):
        decisions.new_item(data, "manual", title, level="superego", source="sync",
                           detail="Skill refresh stopped the sync. Inspect the local sync log and resolve the ownership conflict before retrying.")
        decisions.save(data, home)
PY2
    abort "persona skills refresh failed"
  fi
fi

# Machine guard (Windows only): kills search processes orphaned by a Bash timeout (find/grep/rg, parent dead,
# over 30 min), raises an inbox item on a handle or kernel-pool blow-up, and records vmmemWSL for the weekly
# numbers. Origin: the 3 h `find /` of 28/10/2026 (tools/machine_guard.py).
python -I "$DST/tools/machine_guard.py" hourly || echo "machine guard failed"

# Encrypted secrets backup with an age PUBLIC key (no unlock): tools/secrets_backup.py. Off unless SECRETS_BACKUP=1.
# It runs before the export so a new secrets-manifest.txt line ships in the same run, and writes only .age files into
# the id layer (sealed/secrets); the id repo's commit and push below carry them. Failures go to the decision inbox.
if [ "${SECRETS_BACKUP:-0}" = 1 ]; then
  python -I "$DST/tools/secrets_backup.py" run || echo "secrets backup failed (see the decision inbox)"
fi

# Route every file to its layer (memories and skills by frontmatter `level:`, the rest by layer.json).
# An unlabeled memory or skill goes to the default level (ego) and is listed once in the decision inbox.
python -I "$DST/tools/layers.py" export --manifest "$MANIFEST" --claude-home "$SRC" --all || abort "layer export failed"
# A layer that keeps sealed paths (layer.json `sealed`) ships its own tools/seal.sh; the export skipped the
# plaintext, this writes the fresh .age copies. It needs the age recipient on this machine, so a failure
# only warns.
for l in "${LAYERS[@]}"; do
  lp="${l#*$'	'}"
  [ -x "$lp/tools/seal.sh" ] && { CLAUDE_HOME="$SRC" "$lp/tools/seal.sh" >/dev/null || echo "seal failed for $lp (sealed/ not refreshed)"; }
done
unl="$(python -I "$DST/tools/layers.py" unlabeled --manifest "$MANIFEST" --claude-home "$SRC" | wc -l)"
if [ "$unl" -gt 0 ]; then
  title="Memories or skills without a level (level:) in ~/.claude"
  if ! python -I "$DST/tools/decisions.py" list 2>/dev/null | grep -qF -- "$title"; then
    python -I "$DST/tools/decisions.py" add "$title" --level superego --source sync       --detail "$unl file(s) without level: in the frontmatter went to the default level (ego). Run tools/layers.py unlabeled." >/dev/null || true
  fi
fi

# Delegate runs older than 14 days (each can be a git worktree).
if [ -d "$DST/runs" ]; then
  find "$DST/runs" -mindepth 1 -maxdepth 1 -mtime +14 -exec rm -rf {} + 2>/dev/null || true
  git -C "$DST" worktree prune 2>/dev/null || true
fi

python -I "$DST/tools/search_memory.py" --build --quiet --root "$SRC" || echo "index build failed"
: > "$DST/lint-report.md"
# Each layer is linted with the others as siblings: the layers split one memory tree by level, so an
# index line or a [[link]] that resolves in another layer is not a problem.
SIBLINGS=()
for l in "${LAYERS[@]}"; do lp="${l#*$'	'}"; [ -d "$lp/memory" ] && SIBLINGS+=(--sibling "$lp/memory"); done
for l in "${LAYERS[@]}"; do
  lp="${l#*$'	'}"
  [ -d "$lp/memory" ] || continue
  { echo "# ${l%%$'	'*} ($lp)"; python -I "$DST/tools/lint_memory.py" "$lp/memory" "${SIBLINGS[@]}"; } >> "$DST/lint-report.md" || echo "lint failed for $lp"
done
{ echo; echo "## Graph check (orphans and unresolved links)"; echo; python -I "$DST/tools/graph_view.py" --check | sed "s/^/- /"; } >> "$DST/lint-report.md" || true
# Glossaries (ubiquitous language): one per layer, fixed shape, no undeclared collisions, superego generic.
{ echo; python -I "$DST/tools/lint_glossary.py" --manifest "$MANIFEST" --claude-home "$SRC"; } >> "$DST/lint-report.md" || echo "glossary lint found problems (see lint-report.md)"
render="$(python -I "$DST/tools/render_harness.py" --claude-home "$SRC" --manifest "$MANIFEST" 2>&1)" || echo "codex render failed (over the limit or a layer over its byte budget)"
echo "$render"
# render_harness.py prints "write <path>/AGENTS.md (N bytes)" only when it rewrote the file; the over-limit
# error also mentions AGENTS.md, so match the success line exactly.
RENDERED=0
render="${render//$'\r'/}"
if printf '%s\n' "$render" | grep -q '^write .*AGENTS\.md ([0-9]* bytes)$'; then RENDERED=1; fi
# Byte band (tools/context_budget.py): a layer at 90% or more of its budget keeps its always-loaded files
# (global/*, rules/*; harness/* for the adapter; also under superego/ in the nested layout) out of the commit below, hour after hour, until the layer is
# back under the band (a trim that lands at 95% is still held: the gate is the band, not the direction), and
# gets one open decision item with the cut candidates. Memory, skills and the rest of the layer still sync.
# When the check itself fails, the gate is off for this run and the log says so.
if band_out="$(python -I "$DST/tools/context_budget.py" --list-band --manifest "$MANIFEST" --claude-home "$SRC" 2>&1)"; then
  BAND_LAYERS=" $(printf '%s' "$band_out" | tr -d '\r' | tr '\n' ' ') "
else
  BAND_LAYERS="  "
  echo "warning: budget band check failed, gate off this run: $(printf '%s\n' "$band_out" | tr -d '\r' | tail -1)"
fi
if [ "${BAND_LAYERS// /}" != "" ]; then
  echo "budget band:${BAND_LAYERS}(always-loaded files held back from the commit until trimmed; see the decision inbox)"
  inbox_out="$(python -I "$DST/tools/context_budget.py" --inbox --manifest "$MANIFEST" --claude-home "$SRC" 2>&1)" \
    || echo "inbox add failed: $(printf '%s\n' "$inbox_out" | tr -d '\r' | tail -1)"
fi
held_back() { # level, repo path -> 0 when the path is an always-loaded file of a layer in the band
  case "$2" in
    global/*|rules/*|superego/global/*|superego/rules/*) [[ "$BAND_LAYERS" == *" $1 "* ]] ;;
    harness/*|superego/harness/*) [[ "$BAND_LAYERS" == *" adapter "* ]] ;;
    *) return 1 ;;
  esac
}
echo "Synced from $SRC ($(grep -o '[0-9]* problems' "$DST/lint-report.md" | awk '{ n += $1 } END { if (NR) print n " problems"; else print "lint n/a" }'))"

COMMITTED=0
PUSH_FAILED=0
# Machine output that no layer repo may ever track, whatever its own .gitignore says: harvest digests,
# delegate runs, the search index, generated reports and locks. Kept in .git/info/exclude (local, not
# committed), so a layer repo created or cloned by hand gets the same protection on its first sync.
MACHINE_EXCLUDES=(".harvest/" ".harvest.lock/" ".harvest-pending*.txt" "runs/" "index/" "INDEX.md" "lint-report.md"
  ".work/" ".sync.log" ".sync.lock/" ".memory.lock/" ".*.lock.*" ".*.log" ".*.log.1" "__pycache__/" "*.pyc"
  "scripts/estado/" "decisions/caixa-de-decisoes.html" ".obsidian/workspace*.json" ".obsidian/cache")
ensure_excludes() { # repo path
  local f="$1/.git/info/exclude" pat
  [ -d "$1/.git" ] || return 0
  mkdir -p "$1/.git/info"
  for pat in "${MACHINE_EXCLUDES[@]}"; do
    grep -qxF -- "$pat" "$f" 2>/dev/null || echo "$pat" >> "$f"
  done
}

sync_repo() { # path, level: stage, guard, commit groups, push
  local level="${2:-}"
  cd "$1" || return 1
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "$1 is not a git repo, skipped"; return 0; }
  ensure_excludes "$1"
  # Local stand-in for branch protection (private repos on a free plan have none): no force push or delete of main.
  python -I "$DST/tools/push_guard.py" install "$1" || echo "push guard not installed for $1 (see message above)"
  # A file matched by the excludes that an older sync already tracks is dropped from the index (kept on disk).
  local tracked
  tracked="$(git ls-files -i -c --exclude-standard || true)"
  if [ -n "$tracked" ]; then
    printf '%s\n' "$tracked" | xargs -d '\n' git rm -q --cached -- 2>/dev/null || true
    echo "untracked $(printf '%s\n' "$tracked" | wc -l) machine-output file(s) (kept on disk)"
  fi
  git -c core.safecrlf=false add -A

  # Blob guard: a staged file over 1 MB is unstaged and never committed; one inbox item per file.
  mapfile -d '' staged_now < <(git -c core.quotepath=false diff --cached --name-only --no-renames --diff-filter=AM -z)
  for p in "${staged_now[@]}"; do
    [ -f "$p" ] || continue
    if [ "$(wc -c < "$p")" -gt 1048576 ]; then
      git reset -q -- "$p"
      echo "blocked: $p is over 1 MB and was not committed"
      title="Large file blocked from sync: $p"
      if ! python -I "$DST/tools/decisions.py" list 2>/dev/null | grep -qF -- "$title"; then
        python -I "$DST/tools/decisions.py" add "$title" --level superego --source sync >/dev/null || echo "inbox add failed"
      fi
    fi
  done

  # Abort the commit when a bad mirror would delete a large part of the backup.
  ndel="$(git diff --cached --name-only --no-renames --diff-filter=D | wc -l)"
  if [ "$ndel" -gt 50 ]; then
    git reset -q
    abort "$ndel tracked files would be deleted (limit 50); nothing committed"
  fi

  commit_group() { # message, then the paths of the group
    local msg="$1"; shift
    [ "$#" -gt 0 ] || return 0
    printf '%s\0' "$@" | git -c core.safecrlf=false add -A --pathspec-from-file=- --pathspec-file-nul
    SYNC_COMMIT=1 git commit -q -m "$msg"
    COMMITTED=1
    echo "committed: $msg"
  }
  short_list() { # names on stdin, one per line -> "a, b, c +N more" (max 5)
    awk '!seen[$0]++' | awk -v max=5 '{ n++; if (n <= max) l = l (n > 1 ? ", " : "") $0 } END { if (n > max) l = l " +" (n - max) " more"; print l }'
  }

  mapfile -d '' staged < <(git -c core.quotepath=false diff --cached --name-only --no-renames -z)
  if [ "${#staged[@]}" -eq 0 ]; then
    echo "No changes."
  else
    mem=(); ctx=(); state=(); misc=(); held=()
    for p in "${staged[@]}"; do
      if held_back "$level" "$p"; then held+=("$p"); continue; fi
      case "$p" in
        memory/*) mem+=("$p") ;;
        skills/*|rules/*|global/*|harness/*|scripts/*|plans/*|pdi/*|maps/*) ctx+=("$p") ;;
        decisions/*) state+=("$p") ;;
        *) misc+=("$p") ;;
      esac
    done
    git reset -q
    if [ "${#held[@]}" -gt 0 ]; then
      echo "held back (budget band, $level): ${held[*]}"
    fi
    if [ "${#mem[@]}" -gt 0 ]; then
      projs="$(printf '%s\n' "${mem[@]}" | cut -d/ -f2 | sed -E 's/^[A-Za-z]--Users-[^-]+-//' | short_list)"
      commit_group "chore(memory): sync ${#mem[@]} memories ($projs)" "${mem[@]}"
    fi
    if [ "${#ctx[@]}" -gt 0 ]; then
      names="$(printf '%s\n' "${ctx[@]}" | sed -e 's#^[^/]*/##' -e 's#/.*##' | short_list)"
      commit_group "chore(context): update $names" "${ctx[@]}"
    fi
    if [ "${#state[@]}" -gt 0 ]; then
      commit_group "chore(state): refresh inbox" "${state[@]}"
    fi
    if [ "${#misc[@]}" -gt 0 ]; then
      commit_group "chore(sync): misc" "${misc[@]}"
    fi
  fi

  # Push whenever local is ahead, not only after a new commit: a failed push is retried next hour.
  if git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
    if [ -n "$(git rev-list '@{u}..HEAD')" ]; then
      GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=15" timeout 120 git push -q && echo "Pushed." || echo "push failed, will retry"
      # Local commits stay; the exit code tells the scheduler they are still unpushed.
      if [ -n "$(git rev-list '@{u}..HEAD')" ]; then PUSH_FAILED=1; fi
    fi
  else
    echo "no upstream branch configured, not pushing"
  fi
}
if [ "$PUSH" = 1 ]; then
  for l in "${LAYERS[@]}"; do
    echo "== layer ${l%%$'	'*}: ${l#*$'	'}"
    sync_repo "${l#*$'	'}" "${l%%$'	'*}" || abort "sync of ${l#*$'	'} failed"
  done
  cd "$DST"
  # Public mirror of this repo (HEAD, no history). Off unless PUBLIC_MIRROR=1; a deny hit refuses it.
  public_mirror "$DST" "$DST" || echo "public mirror failed (see above)"
fi

# Release the lock before the slow canary: it must not hold up the next sync.
if [ -z "${SYNC_LOCK_HELD:-}" ]; then lock_release "$LOCK"; fi

# New rules reached Codex: prove a fresh Codex session still loads them (misses go to the decision inbox).
# Once per day, or when this run committed and rewrote AGENTS.md; detached and outside the lock.
if [ "$RENDERED" = 1 ] && { [ "$COMMITTED" = 1 ] || codex_canary_due "$DST"; }; then
  mkdir -p "$DST/.work"
  date +%F > "$DST/.work/codex-canary.stamp"
  nohup python -I "$DST/tools/check_codex.py" >/dev/null 2>&1 &
  echo "codex canary started in the background"
fi
[ "$PUSH_FAILED" = 0 ] || { echo "ABORT: unpushed commits remain after the push attempt" >&2; exit 1; }
