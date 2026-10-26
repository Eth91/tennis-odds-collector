#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# NBA speed layer: nba_watch.py --once, EVERY MINUTE.
# origin: ~/nba-engine/nba_watch.sh (source of truth, in git). The VM runs it in place
# (NBA_SPEED_PREREG.md amendment 4); host config in ~/.nba-engine.env, as in nba_cycle.sh.
#
# Polls through each official injury-report publication (:00/:15/:30/:45 + ~4 s), and on a
# fresh Out for tonight refreshes the books and runs the shadow flag pass at once.
# Within 35 min of a tip it refreshes lines every 2 min (close capture). Shares
# /tmp/nba-cycle.lock with nba_cycle.sh. Bets nothing: nba_flags.LIVE_TIERS is empty.
# Logs only when a run DID something; an idle minute writes nothing. perl alarm = timeout.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
REPO="$HOME/nba-engine"
LOG_DIR="$HOME/cron-jobs"
PY=/usr/local/bin/python3
[ -f "$HOME/.nba-engine.env" ] && . "$HOME/.nba-engine.env"
LOG="$LOG_DIR/nba_watch.log"
cd "$REPO" || { echo "$(date -u +%FT%TZ) FATAL: no $REPO" >>"$LOG"; exit 1; }
# X news source: the VM's underdog-watch.service reads @UnderdogNBA (the burner cookie stays on the
# VM) into a log. On the VM the env file points NBA_X_LOG at it; elsewhere nba_news_watch pulls it
# over ssh with a heartbeat. Neither set = X benched.
if [ -z "${NBA_X_LOG:-}" ]; then
  export NBA_X_SSH="ubuntu@155.248.217.149:/home/ubuntu/tennis-odds-collector/underdog_nba_log.jsonl"
  export NBA_X_KEY="$HOME/.ssh/oracle_vm"
fi
out=$(/usr/bin/perl -e 'alarm shift; exec @ARGV' 170 "$PY" nba_watch.py --once 2>&1); rc=$?
[ -n "$out" ] && printf '%s\n' "$out" >>"$LOG"
[ $rc -ne 0 ] && echo "$(date -u +%FT%TZ) !! nba_watch rc=$rc" >>"$LOG"
[ -f "$LOG" ] && tail -n 8000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit $rc
