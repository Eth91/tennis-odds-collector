#!/bin/bash
# NCAAF FanDuel (Ontario) pre-kickoff ladder on the always-on VM. Cron: */5.
# The Mac sleeps through Saturday games, so the ~T-30 min prices only exist if this box takes them.
# Writes ONLY to ~/ncaaf-prekick/data (never the divergent ~/tennis-odds-collector checkout).
set -u
D=/home/ubuntu/ncaaf-prekick
mkdir -p "$D/data" "$D/logs"
exec 9>"$D/data/.lock"
flock -n 9 || exit 0
LOG=$D/logs/prekick.log
{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  FD_DB_DIR=$D/data /usr/bin/python3 "$D/fd_props.py" poll --league ncaaf --ladder-only --quiet
  echo "exit=$?"
} >> "$LOG" 2>&1
tail -n 20000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
