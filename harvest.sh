#!/usr/bin/env bash
# Hourly: turn sessions the user archived (Claude Code or Codex) into memories and skill drafts, then refresh
# the decision inbox. Sonnet via `claude -p` on the user's login, capped per session, per run and per day.
# Only the ego layer is written to by the passes (harvest log in $EGO/log.md); superego and id memories are
# edited by hand or by context-ingest. Memories land in ~/.claude and reach their layer on the next sync.
# Usage: ./harvest.sh [--manifest ~/Codes/psique/manifest.json] [max_sessions]   (default 6)
set -Eeuo pipefail
echo "== $(date '+%F %T') $0 $*"
trap 'echo "FAILED at line $LINENO (exit $?)" >&2' ERR

REPO="$(cd "$(dirname "$0")" && pwd)"
. "$REPO/lib.sh"
HOME_UNIX="$HOME"
HOME_WIN="$(native_path "$HOME")"
MANIFEST="${SYNC_MANIFEST:-$HOME/Codes/psique/manifest.json}"
MAX=6
while [ $# -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST="$2"; shift ;;
    *) MAX="$1" ;;
  esac
  shift
done
[ -f "$MANIFEST" ] || { echo "harvest: manifest $MANIFEST is missing" >&2; exit 1; }
EGO="$(manifest_layer_path "$MANIFEST" ego)"
[ -n "$EGO" ] && [ -d "$EGO" ] || { echo "harvest: no active ego layer repo in $MANIFEST" >&2; exit 1; }
DAILY_CAP="${HARVEST_DAILY_CAP:-20}"
MAX_TRIES=3
MODEL="${HARVEST_MODEL:-sonnet}"
BUDGET="${HARVEST_BUDGET_USD:-0.60}"   # per session; MAX x BUDGET is the per-run ceiling
OWN="$(tilde_path "$REPO")"   # .harvest/ output folders live in the superego repo
cd "$REPO"
fail() { echo "harvest FAILED ($1)" >&2; exit 1; }

# The weekly pass rewrites memory; never write memory at the same time.
if weekly_running "$REPO"; then echo "weekly pass running, harvest skipped"; exit 0; fi
# .memory.lock is shared with weekly.sh: only one of them writes memory at a time.
LOCK="$REPO/.memory.lock"
if ! lock_acquire "$LOCK" 120; then echo "memory lock busy (weekly or another harvest running), harvest skipped"; exit 0; fi
trap 'lock_release "$LOCK"' EXIT
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN   # subscription login, never per-token billing

mkdir -p .harvest
# Drop session folders older than 7 days (and their retry counters).
find .harvest -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf {} + 2>/dev/null || true
find .harvest -mindepth 1 -maxdepth 1 -type f -name 'retry-*' -mtime +7 -delete 2>/dev/null || true

# Daily cap: .harvest/daily-count holds "<date> <sessions started today>".
today="$(date +%F)"
done_today=0
if [ -f .harvest/daily-count ]; then
  read -r cday cnum < .harvest/daily-count || true
  if [ "${cday:-}" = "$today" ]; then done_today="${cnum:-0}"; fi
fi
room=$((DAILY_CAP - done_today)); [ "$room" -gt 0 ] || room=0
limit="$MAX"; [ "$room" -lt "$limit" ] && limit="$room"

python -I tools/harvest.py pending --max 100000 > .harvest-pending-all.txt || fail pending
total="$(grep -c . .harvest-pending-all.txt || true)"
head -n "$limit" .harvest-pending-all.txt > .harvest-pending.txt
processing="$(grep -c . .harvest-pending.txt || true)"
echo "pending total $total, processing $processing (daily cap $DAILY_CAP, used $done_today)"

while IFS= read -r line; do
  [ -n "$line" ] || continue
  harness="$(python -I -c 'import json,sys; print(json.loads(sys.argv[1])["harness"])' "$line")"
  sid="$(python -I -c 'import json,sys; print(json.loads(sys.argv[1])["id"])' "$line")"
  out=".harvest/$harness-$sid"
  retry_file=".harvest/retry-$harness-$sid"
  tries=0; [ -f "$retry_file" ] && tries="$(cat "$retry_file")"
  if [ "$tries" -ge "$MAX_TRIES" ]; then
    echo "giving up on $harness $sid after $tries failed tries"
    { echo ""; echo "## [$today] harvest | $harness $sid"; echo "- gave up after $tries failed tries"; } >> "$EGO/log.md"
    python -I tools/harvest.py mark "$harness" "$sid"; rm -f "$retry_file"
    continue
  fi
  echo "$today $((done_today + 1))" > .harvest/daily-count; done_today=$((done_today + 1))

  rm -rf "$out" && mkdir -p "$out/out"
  python -I tools/harvest.py digest "$harness" "$sid" > "$out/digest.md" || { python -I tools/harvest.py mark "$harness" "$sid"; continue; }
  sed -e "s#{{OUT}}#$(native_path "$REPO")/$out#g" -e "s#{{HOME}}#$HOME_WIN#g" prompts/harvest.md > "$out/prompt.md"

  rc=0
  timeout 1500 claude -p "Follow the instructions in this message exactly. $(cat "$out/prompt.md")" \
    --model "$MODEL" --max-budget-usd "$BUDGET" --add-dir "$HOME_UNIX/.claude" \
    --allowedTools "Read" "Glob" "Grep" "Edit($OWN/$out/out/**)" \
    --disallowedTools "Bash" "Read(~/.claude/.credentials.json)" "Read(~/.claude/.claude.json)" \
    --output-format text > "$out/claude-output.txt" 2>&1 < /dev/null || rc=$?
  echo "claude exited with $rc" >> "$out/claude-output.txt"

  # Only a clean exit with a summary counts. Otherwise the session stays pending, up to 3 tries.
  if [ "$rc" -ne 0 ] || [ ! -s "$out/out/summary.md" ]; then
    tries=$((tries + 1)); echo "$tries" > "$retry_file"
    echo "harvest of $harness $sid failed (claude exit $rc, summary $([ -s "$out/out/summary.md" ] && echo present || echo missing)); try $tries of $MAX_TRIES"
    continue
  fi

  # Apply: validated memories straight in (as the weekly pass does), skill drafts to the inbox. The
  # validator writes a manifest first; if it fails or any copy fails, nothing is marked and the session
  # stays pending (retry counter).
  manifest="$out/manifest.tsv"
  apply_failed=""
  if ! python -I tools/validate_harvest.py "$out/out/memory" "$HOME_UNIX/.claude/projects" > "$manifest"; then
    apply_failed="validator failed"
  fi
  rejected=""
  if [ -z "$apply_failed" ]; then
    while IFS=$'\t' read -r kind a b; do
      a="${a%$'\r'}"; b="${b%$'\r'}"
      case "$kind" in
        OK)
          proj="${a%%/*}"
          if mkdir -p "$HOME_UNIX/.claude/projects/$proj/memory"              && cp -- "$out/out/memory/$a" "$HOME_UNIX/.claude/projects/$proj/memory/"; then
            echo "memory $a"
          else
            apply_failed="copy failed for $a"; break
          fi ;;
        ADD)
          idx="$HOME_UNIX/.claude/projects/$a/memory/MEMORY.md"
          grep -qxF -- "$b" "$idx" 2>/dev/null || echo "$b" >> "$idx" || { apply_failed="index append failed for $a"; break; } ;;
        REJECT)
          echo "rejected $a: $b"; rejected="$rejected; $a ($b)" ;;
      esac
    done < "$manifest"
  fi
  if [ -n "$apply_failed" ]; then
    tries=$((tries + 1)); echo "$tries" > "$retry_file"
    echo "harvest of $harness $sid not applied ($apply_failed); try $tries of $MAX_TRIES"
    continue
  fi
  for d in "$out"/out/skill-drafts/*/; do
    [ -f "$d/SKILL.md" ] || continue
    if mkdir -p "$HOME_UNIX/.claude/skill-drafts" && cp -r "$d" "$HOME_UNIX/.claude/skill-drafts/"; then
      echo "skill draft $(basename "$d")"
    else
      apply_failed="skill draft copy failed for $(basename "$d")"; break
    fi
  done
  if [ -n "$apply_failed" ]; then
    tries=$((tries + 1)); echo "$tries" > "$retry_file"
    echo "harvest of $harness $sid not fully installed ($apply_failed); try $tries of $MAX_TRIES"
    continue
  fi
  {
    echo ""
    echo "## [$today] harvest | $harness $sid"
    sed 's/^/- /' "$out/out/summary.md"
    [ -z "$rejected" ] || echo "- rejected by validation: ${rejected#; }"
  } >> "$EGO/log.md"
  python -I tools/harvest.py mark "$harness" "$sid"
  rm -f "$retry_file"
done < .harvest-pending.txt

# Self-learning loop (repeats, corrections, decisions). Off unless HARVEST_LEARN=1; budget in tools/learn.py.
if [ "${HARVEST_LEARN:-0}" = "1" ]; then python -I tools/learn.py --ego "$EGO" run || echo "learn failed" >&2; fi

python -I tools/search_memory.py --build --quiet --root "$HOME_UNIX/.claude" || fail index
python -I tools/decisions.py scan > /dev/null || fail scan
echo "harvest done"
