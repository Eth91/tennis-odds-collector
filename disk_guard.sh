#!/usr/bin/env bash
# Disk tripwire for the WNBA box.
#
# WHY: this box has already gone down once from a full disk — 39GB of loose git objects —
# and the failure mode is nasty because every monitor stays GREEN until the moment git
# starts failing. The heartbeat watchdog cannot see it: the loop is alive and ticking, it
# just silently cannot commit or push any more, so the board freezes while everything
# reports healthy. So this watches the one number that predicts that failure.
#
# It also SELF-HEALS at the warn level rather than only shouting, because the cause is
# almost always the same (git objects piling up) and the fix is the same bounded gc the
# daily timer runs.
set -u

WARN=80          # % — start reclaiming
CRIT=90          # % — reclaim AND page the phone
REPO="$HOME/tennis-odds-collector"

pct=$(df --output=pcent / | tail -1 | tr -dc '0-9')
free_h=$(df -h --output=avail / | tail -1 | tr -d ' ')

if [ "$pct" -lt "$WARN" ]; then
  echo "[$(date -u +%H:%M)] disk ${pct}% (${free_h} free) — ok"
  exit 0
fi

echo "[$(date -u +%H:%M)] disk ${pct}% (${free_h} free) — over ${WARN}%, reclaiming"

# Cheap wins first, in increasing order of cost.
sudo journalctl --vacuum-size=50M >/dev/null 2>&1 || true
if [ -d "$REPO/.git" ]; then
  cd "$REPO" || exit 0
  nice -n 19 git reflog expire --expire=now --expire-unreachable=now --all >/dev/null 2>&1 || true
  nice -n 19 git prune --expire=now >/dev/null 2>&1 || true
  nice -n 19 git gc --prune=now --quiet >/dev/null 2>&1 || true
fi

after=$(df --output=pcent / | tail -1 | tr -dc '0-9')
echo "  after reclaim: ${after}%"

# Page only if it is still bad — a successful self-heal is not worth a 3am push.
if [ "$after" -ge "$CRIT" ] && [ -n "${NTFY_TOPIC:-}" ]; then
  curl -s -m 10 -H "Title: WNBA VM disk ${after}%" -H "Priority: urgent" -H "Tags: rotating_light" \
    -d "Disk still ${after}% after automatic reclaim (was ${pct}%). git commits/pushes will start failing silently — the loop keeps ticking and the heartbeat stays green, so nothing else will tell you. SSH in: df -h /; du -sh ~/tennis-odds-collector/.git" \
    "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1 || true
fi
