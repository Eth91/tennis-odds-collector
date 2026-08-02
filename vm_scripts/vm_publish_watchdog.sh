#!/bin/bash
# Watch the MAIN VM's PUBLISHED output from worker-2. The missing half of the watchdog pair.
#
# WHY THIS EXISTS. The main VM published nothing for 19 hours (2026-08-01/02) and every monitor
# read green. Two independent reasons, and closing only one of them would not have helped:
#
#   1. beat() synthesises a parentless commit with git plumbing and force-pushes it, so it never
#      touches the index, HEAD or main. A wedged repo with a dead publisher still emitted a
#      perfectly fresh heartbeat. (Fixed separately: beat() now withholds when the last successful
#      push is over 30 min old.)
#   2. THE WATCHDOG THAT READS THAT HEARTBEAT IS ON GITHUB ACTIONS, AND ACTIONS CRON DOES NOT RUN.
#      vm-watchdog.yml asks for */10. Measured actual gaps over two days: 3h33m, 4h17m, 3h31m,
#      3h33m, 8h29m. So even a correct heartbeat routes into a monitor that can be eight hours
#      late. Fixing (1) alone would have turned a 19-hour outage into an 8-hour one.
#
# So the authoritative monitor moves to a box that is actually always on. This mirrors
# ~/tt_board_watchdog.sh, which already runs on the MAIN VM watching worker-2's board — the pair
# is now symmetric, and each box reports on the other. A watchdog hosted on the box it watches
# cannot report that box being down, which is the whole point of putting this one here.
#
# WHAT IT JUDGES: the PUBLISHED ARTEFACT on origin, not the process, not the heartbeat. Age of the
# newest "vm loop data" commit. That is outcome-based and therefore agnostic to cause — a wedged
# rebase, a full disk, a rejected push, a dead box and a revoked token all look identical to it,
# and all of them are equally "the board is not updating". Unreachable or unparseable counts as
# FAILURE, never as a pass: not knowing is not evidence of health.
#
# Reads the public GitHub API unauthenticated (60 req/h per IP; at */10 this uses 6).
set -u
REPO="fgf9p6ks2f-ux/tennis-odds-collector"
MARKER="vm loop data"
STALE_MIN="${STALE_MIN:-60}"          # loop pushes every ~60s hot and cold; 60 min is ~60 misses
LATCH="$HOME/.vm_publish_alerted"
LOG="$HOME/vm_publish_watchdog.log"

# NTFY_TOPIC lives in the loop env file, not in this script.
[ -f "$HOME/wnba-loop.env" ] && . "$HOME/wnba-loop.env" 2>/dev/null
[ -f "$HOME/tt-loop.env" ]   && . "$HOME/tt-loop.env"   2>/dev/null

say(){ printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >> "$LOG"; }

page(){  # $1 = title, $2 = body, $3 = priority
  [ -n "${NTFY_TOPIC:-}" ] || { say "NO NTFY_TOPIC — cannot page"; return 1; }
  curl -s -m 15 -H "Title: $1" -H "Priority: $3" -d "$2" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1
}

json=$(curl -s -m 20 -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$REPO/commits?per_page=40" 2>/dev/null)

# UNREACHABLE IS A FAILURE, NOT A PASS. An empty body here used to be the shape of a monitor that
# silently stops monitoring; treat it as staleness of unknown age and let the latch rate-limit it.
if [ -z "$json" ]; then
  say "github unreachable"
  if [ ! -f "$LATCH" ]; then
    page "VM publish watchdog blind" "worker-2 cannot reach the GitHub API to check the main VM" default \
      && touch "$LATCH"
  fi
  exit 0
fi

age_min=$(printf '%s' "$json" | python3 -c '
import sys, json, datetime as dt
try:
    d = json.load(sys.stdin)
except Exception:
    print(-1); raise SystemExit
if not isinstance(d, list):
    print(-1); raise SystemExit
now = dt.datetime.now(dt.timezone.utc)
for c in d:
    if "'"$MARKER"'" in (c.get("commit", {}).get("message") or ""):
        t = dt.datetime.fromisoformat(c["commit"]["committer"]["date"].replace("Z", "+00:00"))
        print(int((now - t).total_seconds() // 60)); raise SystemExit
# marker absent from the 40 newest commits = it has not published in a long time, not "fine"
print(9999)
' 2>/dev/null)

case "$age_min" in ''|*[!0-9-]*) age_min=-1 ;; esac

if [ "$age_min" -lt 0 ]; then
  say "unparseable API response"
  exit 0
fi

if [ "$age_min" -gt "$STALE_MIN" ]; then
  say "STALE: main VM last published ${age_min} min ago"
  if [ ! -f "$LATCH" ]; then
    page "Main VM not publishing" \
      "No '$MARKER' commit for ${age_min} min. WNBA + PGA boards are frozen. Check wnba-loop, disk, and whether push is rejected." \
      urgent && touch "$LATCH" && say "paged (latched)"
  fi
else
  if [ -f "$LATCH" ]; then
    rm -f "$LATCH"
    page "Main VM publishing again" "Recovered — last publish ${age_min} min ago" default
    say "RECOVERED (${age_min} min)"
  fi
  say "ok (${age_min} min)"
fi

# self-trim: one line per 10 min is ~144/day and there is no root for logrotate
tail -n 2000 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG" 2>/dev/null
exit 0
