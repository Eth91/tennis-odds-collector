#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# DraftKings sender (Mac) — NBA_SPEED_PREREG.md amendment 4. cron */3.
# DraftKings Akamai-blocks the Oracle VM, where the NBA engine now runs. So the Mac fetches
# DraftKings alone (`nba_lines.py --snapshot dk`) and ships the snapshot to the VM; the VM ingests
# it on its next lines refresh, dated to THIS fetch time. While the Mac sleeps nothing is sent:
# the VM logs DraftKings stale after 10 min, flags price on FanDuel alone after 12, and DraftKings
# only feeds the secondary yardstick — so a sleeping Mac costs nothing in the primary test.
# origin: ~/nba-engine/nba_dk_push.sh (in git). deploy: cp to ~/cron-jobs/nba-dk-push.sh
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
REPO="$HOME/nba-engine"
LOG="$HOME/cron-jobs/nba_dk_push.log"
PY=/usr/local/bin/python3
VM=ubuntu@155.248.217.149
KEY="$HOME/.ssh/oracle_vm"
SNAP=/tmp/nba_dk_snapshot.json
cd "$REPO" || { echo "$(date -u +%FT%TZ) FATAL: no $REPO" >>"$LOG"; exit 1; }
out=$(/usr/bin/perl -e 'alarm shift; exec @ARGV' 120 "$PY" nba_lines.py --snapshot dk "$SNAP" 2>&1); rc=$?
if [ $rc -eq 0 ]; then
  # one connection; write-then-rename so the VM never reads a half-written file
  /usr/bin/perl -e 'alarm shift; exec @ARGV' 60 ssh -i "$KEY" -o ConnectTimeout=15 -o BatchMode=yes "$VM" \
    'cat > nba-engine/dk_snapshot.json.part && mv nba-engine/dk_snapshot.json.part nba-engine/dk_snapshot.json' \
    < "$SNAP"; rc=$?
  [ $rc -ne 0 ] && out="$out · ship to VM failed rc=$rc"
fi
printf '%s rc=%s %s\n' "$(date -u +%FT%TZ)" "$rc" "$(echo "$out" | tr '\n' ' ' | tail -c 300)" >>"$LOG"
[ -f "$LOG" ] && tail -n 4000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit $rc
