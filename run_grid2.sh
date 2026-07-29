#!/bin/bash
# Log OUTSIDE the repo: the loop does `git add -A -f` (which tracks .log files) and then
# reset/replays them, so a long-running job's log inside the repo gets reverted mid-run —
# that is what truncated the first grid log back to its header.
cd ~/tennis-odds-collector || exit 1
pgrep -af '^python3' | grep -F 'tune_half_life' | awk '{print $1}' | xargs -r kill 2>/dev/null
sleep 1
setsid nohup nice -n 15 python3 -u -c "import pga_calib as C; C.tune_half_life()" \
  > ~/halflife.log 2>&1 < /dev/null &
disown
echo "grid restarted, logging to ~/halflife.log"
