#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# NBA cycle (Mac): injuries -> lines -> SHADOW flags -> grade.   Every 10 min.
#
# WHY THE MAC. Every input the NBA engine needs is Mac-only (probed 2026-10-22):
#   cdn.nba.com (slate, box scores)  403s the Oracle VM even with impersonation
#   stats.nba.com (player index)     blocks datacenter IPs
#   DraftKings                       Akamai-blocks the VM by design
# The VM's own copy of nba_flags (vm_loop.sh) cannot see any of them.
#
# NOTHING HERE BETS. nba_flags.LIVE_TIERS is empty: both tiers failed on real lines
# (nba_margin_refit.py; NBA_COLDSTART_PREREG.md). Flags go to nba_shadow.sqlite.
#
# INTERPRETER: /usr/local/bin/python3 — has Full Disk Access, requests and curl_cffi.
# Do NOT use /usr/bin/python3 (no FDA under cron's TCC context; no curl_cffi).
# Each step is logged with its own exit code; a non-zero code is a real alert
# (the scripts exit 2 on a BLIND input instead of reporting a quiet night).
# ─────────────────────────────────────────────────────────────────────────────
# origin: ~/nba-engine/nba_cycle.sh (source of truth, branch nba-realline-arbiter).
# deploy:  cp ~/nba-engine/nba_cycle.sh ~/cron-jobs/nba-cycle.sh
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
# ⚠️ ITS OWN WORKTREE, NOT ~/tennis-odds-collector. That tree is shared with tennis_publish.py
# (cron */15), which runs `git checkout main` in it: on 2026-10-22 09:03 MT it switched the tree
# off this branch, every NBA file vanished from disk, and this cycle failed every 10 min.
# ~/nba-engine is a `git worktree` of branch nba-realline-arbiter; NBA-owned data lives here,
# the shared game-log and odds-history DBs are symlinks into ~/tennis-odds-collector.
REPO="$HOME/nba-engine"
LOG="$HOME/cron-jobs/nba_cycle.log"
LOCK="/tmp/nba-cycle.lock"
PY=/usr/local/bin/python3
stamp(){ date -u +%FT%TZ; }

# one cycle at a time; a lock older than 30 min is a crashed run, not a live one
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then
    rm -rf "$LOCK"; mkdir "$LOCK" || exit 0
    echo "$(stamp) cleared a stale lock" >>"$LOG"
  else
    echo "$(stamp) previous cycle still running — skipped" >>"$LOG"; exit 0
  fi
fi
trap 'rm -rf "$LOCK"' EXIT
cd "$REPO" || { echo "$(stamp) FATAL: no $REPO" >>"$LOG"; exit 1; }

worst=0
run(){  # run <label> <args...>
  local label=$1; shift
  local out rc
  # macOS has no `timeout` (GNU coreutils); perl alarm is the stock equivalent — SIGALRM kills a hung step
  out=$(/usr/bin/perl -e 'alarm shift; exec @ARGV' 300 "$PY" "$@" 2>&1); rc=$?
  printf '%s %-6s rc=%s %s\n' "$(stamp)" "$label" "$rc" "$(echo "$out" | tr '\n' ' ' | cut -c1-900)" >>"$LOG"
  [ $rc -gt $worst ] && worst=$rc
  return 0
}
run inj    nba_injuries.py
run lines  nba_lines.py
run flags  nba_flags.py
run grade  nba_flags.py --grade

# bounded log
[ -f "$LOG" ] && tail -n 8000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit $worst
