#!/usr/bin/env bash
# Weekly LLM maintenance (lint + compile) of the Claude context, then sync and push.
# Only the ego layer's memory, log, proposals and reports are maintained here; superego and id memories are
# edited by hand or by context-ingest. Tools, prompts, .work/ and locks stay in this (superego) repo.
# Usage: ./weekly.sh [--manifest ~/Codes/psique/manifest.json] [days_back]
#        (default window: since the newest $EGO/reports/*.md, at most 28 days)
set -Eeuo pipefail
echo "== $(date '+%F %T') $0 $*"
trap 'echo "FAILED at line $LINENO (exit $?)" >&2' ERR

REPO="$(cd "$(dirname "$0")" && pwd)"
. "$REPO/lib.sh"
REPO_WIN="$(native_path "$REPO")"
HOME_UNIX="$HOME"
HOME_WIN="$(native_path "$HOME")"
DATE="$(date +%F)"
MANIFEST="${SYNC_MANIFEST:-$HOME/Codes/psique/manifest.json}"
DAYS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST="$2"; shift ;;
    *) DAYS="$1" ;;
  esac
  shift
done
[ -f "$MANIFEST" ] || { echo "weekly: manifest $MANIFEST is missing" >&2; exit 1; }
EGO="$(manifest_layer_path "$MANIFEST" ego)"
[ -n "$EGO" ] && [ -d "$EGO" ] || { echo "weekly: no active ego layer repo in $MANIFEST" >&2; exit 1; }
EGO_WIN="$(native_path "$EGO")"
MODEL="${WEEKLY_MODEL:-sonnet}"
BUDGET="${WEEKLY_BUDGET_USD:-3}"

cd "$REPO"
# Default window: since the newest report, never more than 28 days back (an explicit argument wins).
if [ -n "$DAYS" ]; then
  SINCE="$(date -d "$DAYS days ago" +%F)"
else
  SINCE="$(date -d "28 days ago" +%F)"
  last="$(ls "$EGO"/reports/*.md 2>/dev/null | sed -e 's#.*/##' -e 's#\.md$##' | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' | sort | tail -1 || true)"
  if [ -n "$last" ] && [[ "$last" > "$SINCE" ]]; then SINCE="$last"; fi
fi

# Always run on the user's Claude login (subscription), never on an API key that would bill per token.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN

# Hold .sync.lock for the whole run so the hourly sync cannot touch memory/ between our steps. Wait for a
# sync that is running right now, but not forever.
SYNC_LOCK="$REPO/.sync.lock"
if ! lock_wait "$SYNC_LOCK" "${WEEKLY_LOCK_WAIT_S:-600}" 120; then
  echo "weekly: .sync.lock stayed busy for ${WEEKLY_LOCK_WAIT_S:-600} s" >&2
  exit 1
fi
# .memory.lock is shared with harvest.sh: only one of them writes memory at a time.
MEM_LOCK="$REPO/.memory.lock"
cleanup() { rm -f "$REPO/.work/weekly.lock"; lock_release "$MEM_LOCK"; lock_release "$SYNC_LOCK"; }
trap cleanup EXIT
if ! lock_wait "$MEM_LOCK" "${WEEKLY_LOCK_WAIT_S:-600}" 180; then
  echo "weekly: .memory.lock (harvest running?) stayed busy for ${WEEKLY_LOCK_WAIT_S:-600} s" >&2
  exit 1
fi
export SYNC_LOCK_HELD=1
export SYNC_REQUIRE=1   # a skipped baseline or final sync must fail the weekly run

canary_stamp="$(cat .work/codex-canary.stamp 2>/dev/null || true)"
./sync.sh --push --manifest "$MANIFEST"   # baseline commit, so the weekly commit holds only the model changes
canary_stamp="$(cat .work/codex-canary.stamp 2>/dev/null || echo "$canary_stamp")"
rm -rf .work && mkdir -p .work "$EGO/reports"
[ -n "$canary_stamp" ] && echo "$canary_stamp" > .work/codex-canary.stamp
touch "$EGO/log.md" "$EGO/proposals.md"
python -I tools/extract_prompts.py --since "$SINCE" > .work/prompts.md
python -I tools/decay.py > .work/decay.txt || echo "decay failed" >> .work/decay.txt   # dormant items -> decision inbox
if [ "${HARVEST_LEARN:-0}" = "1" ]; then python -I tools/learn.py --ego "$EGO" effects --report "$EGO/reports/learning-$DATE.md" > /dev/null || echo "learn effects failed" >> .work/decay.txt; fi   # before/after of approved learn proposals
if codex_canary_due "$REPO"; then
  python -I tools/check_codex.py > .work/codex-canary.txt 2>&1 || echo "codex canary failed" >> .work/codex-canary.txt
  date +%F > .work/codex-canary.stamp
else
  echo "skipped: sync already ran the Codex canary today (misses are in the decision inbox)" > .work/codex-canary.txt
fi

# Docker left behind by validation sessions: prune stopped containers (>24 h), build cache (>7 d) and dangling
# images; containers unhealthy for 2 h+ go to the decision inbox, never removed here (tools/machine_guard.py).
python -I tools/machine_guard.py weekly > .work/machine.txt 2>&1 || echo "machine guard failed" >> .work/machine.txt

sed -e "s#{{DATE}}#$DATE#g" -e "s#{{SINCE}}#$SINCE#g" -e "s#{{REPO}}#$REPO_WIN#g" -e "s#{{EGO}}#$EGO_WIN#g" -e "s#{{HOME}}#$HOME_WIN#g" \
  prompts/weekly-maintenance.md > .work/prompt.md

OWN="$(tilde_path "$REPO")"    # tools, .work/ (superego)
EGO_P="$(tilde_path "$EGO")"   # memory, log, proposals, reports (ego)
# The model edits the ego repo copy of memory/ (Claude Code protects ~/.claude from writes); the wrapper
# copies the changed files back. weekly.lock tells harvest to stay away meanwhile.
touch .work/weekly.lock
rc=0
timeout 1500 claude -p "Follow the instructions in this message exactly." \
  --model "$MODEL" --max-budget-usd "$BUDGET" --add-dir "$HOME_UNIX/.claude" --add-dir "$EGO" \
  --allowedTools "Read" "Glob" "Grep" \
    "Edit($EGO_P/memory/**)" "Edit($EGO_P/log.md)" "Edit($EGO_P/proposals.md)" \
    "Edit($EGO_P/reports/**)" "Edit($OWN/.work/**)" \
  --disallowedTools "Bash" "Read(~/.claude/.credentials.json)" "Read(~/.claude/.claude.json)" \
  --output-format text < .work/prompt.md > .work/claude-output.txt 2>&1 || rc=$?
echo "claude exited with $rc" >> .work/claude-output.txt

# The model step only counts when it left the report behind.
if [ "$rc" -ne 0 ] || [ ! -s "$EGO/reports/$DATE.md" ]; then
  echo "weekly FAILED: claude exit $rc, reports/$DATE.md $([ -s "$EGO/reports/$DATE.md" ] && echo present || echo missing)" >&2
  python -I tools/decisions.py add "weekly failed on $DATE" --source weekly \
    --detail "claude exited with $rc; reports/$DATE.md missing or empty in the ego layer. See .work/claude-output.txt in superego." \
    || echo "inbox add failed" >&2
  exit 1
fi

# From here on the steps work on the ego repo: memory/<project>/<file> paths are relative to it, while
# .work/ stays in the superego repo ($REPO).
cd "$EGO"

# A memory in ~/.claude that changed since the baseline commit must survive: compare it with HEAD.
unchanged_since_baseline() { # repo-relative file, destination
  local f="$1" dest="$2"
  if [ ! -f "$dest" ]; then
    # Gone from ~/.claude since the baseline commit: that is a conflict, never recreate it.
    if git cat-file -e "HEAD:$f" 2>/dev/null; then return 1; fi
    return 0
  fi
  git cat-file -e "HEAD:$f" 2>/dev/null || return 1
  git show "HEAD:$f" | cmp -s - "$dest"
}
# Copy through a sibling temp file and rename, so a failed copy never truncates live memory.
safe_copy() { # source, destination
  local tmp="$2.weekly-tmp.$$"
  if cp -- "$1" "$tmp" && mv -f -- "$tmp" "$2"; then return 0; fi
  rm -f -- "$tmp"
  return 1
}
valid_memory() { [[ "$1" =~ ^memory/[^/]+/[^/]+\.md$ ]] && [[ "$1" != *..* ]]; }

# Files the model marked as merged: memory/<project>/<file>.md, never an index.
if [ -f "$REPO/.work/delete.txt" ]; then
  while IFS= read -r f; do
    f="${f%$'\r'}"; f="${f#./}"
    valid_memory "$f" || continue
    case "$f" in
      memory/*/MEMORY.md) ;;
      *)
        proj="$(basename "$(dirname "$f")")"
        dest="$HOME_UNIX/.claude/projects/$proj/memory/$(basename "$f")"
        if unchanged_since_baseline "$f" "$dest"; then
          rm -f -- "$f" "$dest" && echo "deleted $f"
        else
          rm -f -- "$f"; echo "conflict: $dest changed since the baseline, kept it (deleted only the repo copy)"
        fi ;;
    esac
  done < "$REPO/.work/delete.txt"
fi

# Copy new or changed memory files back to ~/.claude.
while IFS= read -r line; do
  f="${line:3}"
  valid_memory "$f" || continue
  [ -f "$f" ] || continue
  proj="$(basename "$(dirname "$f")")"
  dest="$HOME_UNIX/.claude/projects/$proj/memory/$(basename "$f")"
  mkdir -p "$HOME_UNIX/.claude/projects/$proj/memory" || { echo "weekly FAILED: mkdir for $proj" >&2; exit 1; }
  if unchanged_since_baseline "$f" "$dest"; then
    safe_copy "$f" "$dest" || { echo "weekly FAILED: could not copy $f to $dest" >&2; exit 1; }
    echo "applied $f"
  else
    safe_copy "$f" "$dest.weekly-conflict" || { echo "weekly FAILED: could not write $dest.weekly-conflict" >&2; exit 1; }
    echo "conflict: $dest changed or vanished since the baseline; weekly version saved as $(basename "$dest").weekly-conflict"
  fi
done < <(git -c core.quotepath=false status --porcelain --untracked-files=all -- memory/)
rm -f "$REPO/.work/weekly.lock"

python -I "$REPO/tools/decisions.py" scan > /dev/null || echo "inbox scan failed"
# The model's changes (memory, log.md, proposals.md, reports) as one maintenance commit; sync pushes it.
git -c core.safecrlf=false add -A
if ! git diff --cached --quiet; then git commit -q -m "chore(weekly): $DATE maintenance pass"; fi
"$REPO/sync.sh" --push --manifest "$MANIFEST"
echo "weekly done: $EGO/reports/$DATE.md"
