#!/bin/bash
cd ~/tennis-odds-collector || exit 1
python3 - <<'PY'
import sqlite3
import pga_holes as H
c = sqlite3.connect(str(H.DB))
c.execute("DROP TABLE IF EXISTS course_holes")
c.commit(); c.close()
print("  dropped stale 12-column table")
PY
setsid nohup nice -n 10 python3 -u pga_holes.py > ~/holes.log 2>&1 < /dev/null &
disown
echo "harvest restarted"
