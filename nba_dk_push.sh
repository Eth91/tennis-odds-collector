#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# DraftKings sender (Mac) — NBA_SPEED_PREREG.md amendment 4. cron */3.
# DraftKings Akamai-blocks the Oracle VM, where the NBA engine now runs. So the Mac fetches
# DraftKings alone (`nba_lines.py --snapshot dk`) and ships the snapshot to the VM's receiver
# (nba_dk_receive.py: validates, keeps whichever snapshot is newest); the VM ingests it on its next
# lines refresh, dated to THIS fetch time. Since 2026-10-23 GitHub Actions (nba-dk.yml) sends
# DraftKings through the game-day window; this is the second sender, for whenever the Mac is awake. While the Mac sleeps nothing is sent:
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
  # the receiver validates and writes atomically, and never replaces a newer snapshot
  recv=$(/usr/bin/perl -e 'alarm shift; exec @ARGV' 60 ssh -i "$KEY" -o ConnectTimeout=15 -o BatchMode=yes "$VM" \
    'python3 nba-engine/nba_dk_receive.py' < "$SNAP" 2>&1); rc=$?
  out="$out · VM: $recv"
  [ $rc -ne 0 ] && out="$out · ship to VM failed rc=$rc"
fi
printf '%s rc=%s %s\n' "$(date -u +%FT%TZ)" "$rc" "$(echo "$out" | tr '\n' ' ' | tail -c 300 | iconv -c -f UTF-8 -t UTF-8 2>/dev/null)" >>"$LOG"
# NFL (nfl_lines.py): the same send for DraftKings' NFL board, after the NBA one; the receiver writes an NFL-marked
# snapshot to its own file. Logged on its own line; it never changes this script's exit code. Skipped while this
# checkout has no nfl_lines.py (a branch without the NFL side).
if [ -f nfl_lines.py ]; then
  NSNAP=/tmp/nfl_dk_snapshot.json
  nout=$(/usr/bin/perl -e 'alarm shift; exec @ARGV' 90 "$PY" nfl_lines.py --snapshot dk "$NSNAP" 2>&1); nrc=$?
  if [ $nrc -eq 0 ]; then
    nrecv=$(/usr/bin/perl -e 'alarm shift; exec @ARGV' 45 ssh -i "$KEY" -o ConnectTimeout=15 -o BatchMode=yes "$VM" \
      'python3 nba-engine/nba_dk_receive.py' < "$NSNAP" 2>&1); nrc=$?
    nout="$nout · VM: $nrecv"
  fi
  printf '%s nfl rc=%s %s\n' "$(date -u +%FT%TZ)" "$nrc" "$(echo "$nout" | tr '\n' ' ' | tail -c 300 | iconv -c -f UTF-8 -t UTF-8 2>/dev/null)" >>"$LOG"
fi
[ -f "$LOG" ] && tail -n 4000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit $rc
