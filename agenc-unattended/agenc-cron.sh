#!/usr/bin/env bash
# Run one AgenC job unattended (cron, systemd timer, CI). Writes a patch for
# human review; never commits, pushes or deploys.
#
# Usage: agenc-cron.sh [--dry-run]
# Config (env):
#   JOB         job name, e.g. nightly-lint            (required)
#   REPO        path to the git repo                   (required)
#   BRIEF       path to the brief file                 (required)
#   CHECK       done command run in the worktree, e.g. "pytest -q" (required)
#   PROVIDER, MODEL   passed to --provider/--model     (required)
#   BASE        ref to start from                      (default: main)
#   JOB_KEY     idempotency key                        (default: $JOB-YYYY-MM-DD)
#   CALLS       --task-max-calls                       (default: 30)
#   DEADLINE    --deadline seconds                     (default: 900)
#   MODE        --permission-mode                      (default: acceptEdits)
#   MAX_ATTEMPTS  attempts per key before escalating   (default: 3)
#   STATE_DIR   locks, logs, results                   (default: ~/.local/state/agenc-jobs)
#   ALERT_CMD   command that receives the alert text on stdin (default: write to stderr)
# Exit: 0 done or skipped, 1 job failed (alerted), 2 config error, 3 escalated.
set -euo pipefail

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

: "${JOB:?set JOB}" "${REPO:?set REPO}" "${BRIEF:?set BRIEF}" "${CHECK:?set CHECK}"
: "${PROVIDER:?set PROVIDER}" "${MODEL:?set MODEL}"
BASE="${BASE:-main}"
JOB_KEY="${JOB_KEY:-$JOB-$(date +%F)}"
CALLS="${CALLS:-30}"
DEADLINE="${DEADLINE:-900}"
MODE="${MODE:-acceptEdits}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-3}"
STATE_DIR="${STATE_DIR:-$HOME/.local/state/agenc-jobs}"
OUT="$STATE_DIR/$JOB_KEY"
WT="$STATE_DIR/wt-$JOB_KEY"

log() { printf '%s [%s] %s\n' "$(date -u +%FT%TZ)" "$JOB_KEY" "$*" >&2; }
alert() {
  local msg="agenc job $JOB_KEY: $*"
  log "ALERT: $*"
  if [[ -n "${ALERT_CMD:-}" && $DRY -eq 0 ]]; then printf '%s\n' "$msg" | sh -c "$ALERT_CMD" || log "alert command failed"; fi
}
run() { if (( DRY )); then printf 'DRY-RUN:'; printf ' %q' "$@"; printf '\n'; else "$@"; fi; }

[[ -f "$BRIEF" ]] || { log "brief not found: $BRIEF"; exit 2; }
git -C "$REPO" rev-parse --verify --quiet "$BASE^{commit}" >/dev/null || { log "bad BASE: $BASE"; exit 2; }
mkdir -p "$OUT"

# 1. One run at a time per job. A second firing exits quietly.
exec 9>"$STATE_DIR/$JOB.lock"
if ! flock -n 9; then log "previous run still active; skipping"; exit 0; fi

# 2. Idempotent: a finished or escalated key never runs again.
if [[ -e "$OUT/done" ]]; then log "already done; skipping"; exit 0; fi
if [[ -e "$OUT/ESCALATED" ]]; then log "escalated; waiting for a human"; exit 3; fi
attempt=$(( $(cat "$OUT/attempts" 2>/dev/null || echo 0) + 1 ))
(( DRY )) || echo "$attempt" > "$OUT/attempts"
log "attempt $attempt of $MAX_ATTEMPTS"

# 3. Fresh worktree from BASE on every attempt.
run git -C "$REPO" worktree remove --force "$WT" 2>/dev/null || true
run git -C "$REPO" worktree add --detach "$WT" "$BASE"

# 4. Capped, sandboxed, non-interactive run. Results land outside the worktree.
set +e
if (( DRY )); then
  run agenc --provider "$PROVIDER" --model "$MODEL" --permission-mode "$MODE" \
    --task-max-calls "$CALLS" --deadline "+$DEADLINE" --deadline-reserve 60 \
    --output-format json -p "<contents of $BRIEF>"
  rc=0
else
  ( cd "$WT" && timeout $(( DEADLINE + 120 )) agenc --provider "$PROVIDER" --model "$MODEL" \
      --permission-mode "$MODE" --task-max-calls "$CALLS" --deadline "+$DEADLINE" \
      --deadline-reserve 60 --output-format json -p "$(cat "$BRIEF")" \
      > "$OUT/result.$attempt.json" 2> "$OUT/agenc.$attempt.err" )
  rc=$?
fi
(( DRY )) || echo "$rc" > "$OUT/exit.$attempt"
log "agenc exit=$rc"

crc=-1
# 5. The wrapper runs the done command itself. The agent's claim is not proof.
if (( rc == 0 )); then
  if (( DRY )); then run sh -c "cd $WT && $CHECK"; crc=0
  else ( cd "$WT" && sh -c "$CHECK" ) > "$OUT/check.$attempt.log" 2>&1; crc=$?; fi
  log "check exit=$crc"
fi
set -e

if (( rc == 0 && crc == 0 )); then
  if (( DRY )); then run git -C "$WT" diff --binary
  else
    git -C "$WT" add -A
    git -C "$WT" diff --cached --binary "$BASE" > "$OUT/change.patch"
    touch "$OUT/done"
  fi
  log "done; patch for review: $OUT/change.patch"
  exit 0
fi

# 6. Failure: alert every time; escalate after the last attempt.
reason="agenc exit=$rc"
(( crc >= 0 )) && reason+=" check exit=$crc"
reason+="; logs in $OUT"
if (( attempt >= MAX_ATTEMPTS )); then
  if (( DRY == 0 )); then
    { echo "goal: see $BRIEF"; echo "attempts: $attempt"
      for i in $(seq 1 "$attempt"); do echo "attempt $i exit=$(cat "$OUT/exit.$i" 2>/dev/null)"; done
      echo "needed: a human decision; re-brief, split, or drop this job"; } > "$OUT/ESCALATED"
  fi
  alert "ESCALATED after $attempt failed attempts; $reason"
  exit 3
fi
alert "attempt $attempt failed; $reason"
exit 1
