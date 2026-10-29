#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# NBA cycle: official report -> lines -> SHADOW flags -> grade.
# cron 3-59/10 — offset from the :00/:15/:30/:45 report marks so nba_watch (every minute)
# holds the shared lock when a report publishes, not this job.
#
# WHERE (NBA_SPEED_PREREG.md amendment 4, 2026-10-23): the always-on Oracle VM, ~/nba-engine.
# It reaches every input except DraftKings (verified 2026-10-23 — the earlier "cdn.nba.com 403s
# the VM" was a 403 on a game file that did not exist yet). DraftKings arrives as a snapshot the
# Mac pushes (nba_dk_push.sh); NBA_DK_SNAPSHOT names it. The Mac ran this until the cutover.
#
# HOST CONFIG: ~/.nba-engine.env, if present, overrides PY / LOG_DIR and exports NBA_BOOKS,
# NBA_DK_SNAPSHOT, NBA_X_LOG. No file = the Mac defaults below.
#
# NOTHING HERE BETS. nba_flags.LIVE_TIERS is empty. Flags go to nba_shadow.sqlite.
#
# INTERPRETER (Mac): /usr/local/bin/python3 — has Full Disk Access, requests and curl_cffi.
# Do NOT use /usr/bin/python3 there (no FDA under cron's TCC context; no curl_cffi).
# Each step is logged with its own exit code; a non-zero code is a real alert
# (the scripts exit 2 on a BLIND input instead of reporting a quiet night).
# ─────────────────────────────────────────────────────────────────────────────
# origin: ~/nba-engine/nba_cycle.sh (source of truth, in git). The VM runs it in place.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
REPO="$HOME/nba-engine"
LOG_DIR="$HOME/cron-jobs"
PY=/usr/local/bin/python3
[ -f "$HOME/.nba-engine.env" ] && . "$HOME/.nba-engine.env"
LOG="$LOG_DIR/nba_cycle.log"
LOCK="/tmp/nba-cycle.lock"
stamp(){ date -u +%FT%TZ; }

# --- lock: one cycle at a time; a lock older than 30 min is a crashed run, not a live one
# a plain FILE at the lock path is stray (amendment 17): the lock is a directory
# wait up to LOCK_WAIT_S for a per-minute nba_watch run (the reaction follow) to let go, rather than skipping at once:
# on 2026-10-28 every :03/:13/... cycle lost to it, so DraftKings (refreshed only here) went stale
[ -e "$LOCK" ] && [ ! -d "$LOCK" ] && rm -f "$LOCK"
LOCK_WAIT_S=${LOCK_WAIT_S:-120}
got=""
for _ in $(seq 1 $((LOCK_WAIT_S / 2))); do
  if mkdir "$LOCK" 2>/dev/null; then got=1; break; fi
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then
    rm -rf "$LOCK"
    if mkdir "$LOCK" 2>/dev/null; then got=1; echo "$(stamp) cleared a stale lock" >>"$LOG"; break; fi
  fi
  sleep 2
done
if [ -z "$got" ]; then
  echo "$(stamp) previous cycle still running after ${LOCK_WAIT_S}s — skipped" >>"$LOG"; exit 0
fi
trap 'rm -rf "$LOCK"' EXIT
# --- end lock
cd "$REPO" || { echo "$(stamp) FATAL: no $REPO" >>"$LOG"; exit 1; }

worst=0
run(){  # run <label> <args...>
  local label=$1; shift
  local out rc
  # macOS has no `timeout` (GNU coreutils); perl alarm is the stock equivalent — SIGALRM kills a hung step
  out=$(/usr/bin/perl -e 'alarm shift; exec @ARGV' 300 "$PY" "$@" 2>&1); rc=$?
  # keep the END of the output: summaries, BLIND reasons and errors print last, and the first
  # version kept the head, so a step's flag lines hid its own exit reason (2026-10-23)
  printf '%s %-6s rc=%s %s\n' "$(stamp)" "$label" "$rc" "$(echo "$out" | tr '\n' ' ' | tail -c 1200 | iconv -c -f UTF-8 -t UTF-8 2>/dev/null)" >>"$LOG"
  [ $rc -gt $worst ] && worst=$rc
  return 0
}
run report nba_injury_report.py
run lines  nba_lines.py
run flags  nba_flags.py
run grade  nba_flags.py --grade

# bounded log
[ -f "$LOG" ] && tail -n 8000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit $worst
