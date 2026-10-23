#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# NBA speed layer (Mac): nba_watch.py --once, EVERY MINUTE.
# origin: ~/nba-engine/nba_watch.sh (source of truth, in git).
# deploy:  cp ~/nba-engine/nba_watch.sh ~/cron-jobs/nba-watch.sh
#
# Polls through each official injury-report publication (:00/:15/:30/:45 + ~4 s), and on a
# fresh Out for tonight refreshes FanDuel + DraftKings and runs the shadow flag pass at once.
# Within 35 min of a tip it refreshes lines every 2 min (close capture). Shares
# /tmp/nba-cycle.lock with nba-cycle.sh. Bets nothing: nba_flags.LIVE_TIERS is empty.
# Logs only when a run DID something; an idle minute writes nothing.
# Interpreter /usr/local/bin/python3 (Full Disk Access + curl_cffi); perl alarm = timeout.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
REPO="$HOME/nba-engine"
LOG="$HOME/cron-jobs/nba_watch.log"
cd "$REPO" || { echo "$(date -u +%FT%TZ) FATAL: no $REPO" >>"$LOG"; exit 1; }
# X news source: the VM's underdog-watch.service reads @UnderdogNBA (the burner cookie stays on the
# VM) into this log; nba_news_watch pulls it over ssh with a heartbeat. Unset = X benched.
export NBA_X_SSH="ubuntu@155.248.217.149:/home/ubuntu/tennis-odds-collector/underdog_nba_log.jsonl"
export NBA_X_KEY="$HOME/.ssh/oracle_vm"
out=$(/usr/bin/perl -e 'alarm shift; exec @ARGV' 170 /usr/local/bin/python3 nba_watch.py --once 2>&1); rc=$?
[ -n "$out" ] && printf '%s\n' "$out" >>"$LOG"
[ $rc -ne 0 ] && echo "$(date -u +%FT%TZ) !! nba_watch rc=$rc" >>"$LOG"
[ -f "$LOG" ] && tail -n 8000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit $rc
