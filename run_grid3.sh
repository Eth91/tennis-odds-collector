#!/bin/bash
# Run the grid against a SNAPSHOT outside the repo.
#
# The first run died at the 270-day point with "database disk image is malformed" — not real
# corruption (integrity_check came back ok with all 65,359 rounds) but the loop replacing the
# TRACKED pga_model.sqlite underneath a long-held read handle. Same root cause as the earlier
# "attempt to write a readonly database". A snapshot makes long jobs immune.
#
# 120 and 180 are re-run deliberately: if they reproduce the live-DB numbers, the earlier
# points are trustworthy and only the tail needed redoing.
cd ~/tennis-odds-collector || exit 1
pgrep -af '^python3' | grep -F 'tune_half_life' | awk '{print $1}' | xargs -r kill 2>/dev/null
cp -f pga_model.sqlite ~/pga_model_snap.sqlite
python3 -c "
import sqlite3
c = sqlite3.connect('$HOME/pga_model_snap.sqlite')
print('snapshot: %s rounds, integrity %s' % (
    c.execute('SELECT COUNT(*) FROM rounds').fetchone()[0],
    c.execute('PRAGMA integrity_check').fetchone()[0]))
"
setsid nohup nice -n 15 python3 -u -c "
import os
import pga_ruler as RU
RU.DB = os.path.expanduser('~/pga_model_snap.sqlite')
import pga_calib as C
C.RU = RU
C.tune_half_life(grid=(120, 180, 270, 365, 100000))
" > ~/halflife2.log 2>&1 < /dev/null &
disown
echo "grid running on snapshot -> ~/halflife2.log"
