#!/bin/bash
cd ~/tennis-odds-collector || exit 1
python3 - <<'PY'
import os, shutil, sqlite3
import pga_ruler as RU
# snapshot BEFORE so the comparison is apples-to-apples and the loop cannot swap the DB mid-run
con = sqlite3.connect(RU.DB)
b = con.execute("SELECT COUNT(*), COUNT(DISTINCT player), COUNT(DISTINCT event_id) FROM rounds").fetchone()
con.close()
print("BEFORE: %d rounds, %d players, %d events" % b)
R, _ = RU.fit()
thin = sum(1 for v in R.values() if v[2] < RU.MIN_ROUNDS)
print("        %d of %d rated players below MIN_ROUNDS=%d (%.0f%%)"
      % (thin, len(R), RU.MIN_ROUNDS, 100*thin/len(R)))
PY
echo "=== crawling pga + eur, 2023-2026 ==="
nice -n 10 timeout 1500 python3 -c "
import pga_ruler as RU
RU.crawl(seasons=(2023,2024,2025,2026), leagues=('pga','eur'))
" 2>&1 | tail -12
python3 - <<'PY'
import sqlite3
import pga_ruler as RU
con = sqlite3.connect(RU.DB)
a = con.execute("SELECT COUNT(*), COUNT(DISTINCT player), COUNT(DISTINCT event_id) FROM rounds").fetchone()
con.close()
print("AFTER : %d rounds, %d players, %d events" % a)
R, _ = RU.fit()
thin = sum(1 for v in R.values() if v[2] < RU.MIN_ROUNDS)
print("        %d of %d rated players below MIN_ROUNDS=%d (%.0f%%)"
      % (thin, len(R), RU.MIN_ROUNDS, 100*thin/len(R)))
PY
