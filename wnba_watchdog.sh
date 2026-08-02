#!/usr/bin/env bash
# wnba-loop heartbeat watchdog — the local half of the dead-man's switch.
#
# There are now TWO heartbeats and they answer different questions:
#
#   heartbeat BRANCH (git push, checked by vm-watchdog.yml on Actions)
#       "is the box alive and can it reach GitHub?" — must run OFF the VM, and can only
#       alert the phone, never fix anything.
#
#   .wnba_loop_beat (this one, local file)
#       "is the loop actually TICKING?" — no network, no token, so it stays truthful when
#       git is the thing that is wedged. That distinction matters: a blocked push used to
#       look identical to a dead loop.
#
# This exists because cutting the Actions crons removed the accidental backstop — Actions
# used to re-run the WNBA steps on its own schedule, so a wedged VM loop degraded rather
# than stopped. Now the VM is the only runner, and `Restart=always` does not help when the
# process is alive but stuck on a hung socket.
#
# STALE = 600s. A normal cold tick is 75s; the worst legitimate tick is the 4h slow block
# (lineup_model + redist + clv report), which the loop also beats through, so 10 minutes is
# well clear of normal while still recovering fast enough to matter inside a hot window.
BEAT="$HOME/.wnba_loop_beat"
STALE_S=600
set -a; . "$HOME/wnba-loop.env" 2>/dev/null; set +a

now=$(date -u +%s)
last=$(cat "$BEAT" 2>/dev/null || echo 0)
age=$(( now - last ))
active=$(systemctl is-active wnba-loop 2>/dev/null)

# A stopped service is a deliberate act (maintenance) — do not fight the operator.
if [ "$active" != "active" ]; then
  echo "[$(date -u +%H:%M)] wnba-loop is '$active' — not restarting (assumed intentional)"
  exit 0
fi

if [ "$last" -eq 0 ]; then
  echo "[$(date -u +%H:%M)] no heartbeat file yet — loop may still be starting"
  exit 0
fi

if [ "$age" -gt "$STALE_S" ]; then
  echo "[$(date -u +%H:%M)] WEDGED: heartbeat ${age}s old (>${STALE_S}s) — restarting wnba-loop"
  sudo -n /bin/systemctl restart wnba-loop
  if [ -n "$NTFY_TOPIC" ]; then
    curl -s -m 10 -H "Title: WNBA loop wedged" -H "Priority: high" -H "Tags: rotating_light" \
      -d "wnba-loop heartbeat was ${age}s stale — service restarted. Actions no longer backstops WNBA, so check journalctl -u wnba-loop for what it was stuck on." \
      "https://ntfy.sh/$NTFY_TOPIC" >/dev/null || true
  fi
else
  echo "[$(date -u +%H:%M)] ok — heartbeat ${age}s old"
fi
