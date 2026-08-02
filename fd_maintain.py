#!/usr/bin/env python3
"""fanduel_props.sqlite maintenance (2026-07-27: the DB is no longer committed to git —
95.6MB vs GitHub's 100MB hard limit — so the repo is no longer its backup).
  1. hot snapshot via VACUUM INTO (safe on a live DB) -> fanduel_props.bak.sqlite
  2. prune fd_lines older than KEEP_DAYS (CLV needs ~2 days; meters ~30)
Runs daily on the VM (cron). Both steps are no-ops if the DB is missing."""
import datetime as dt
import os
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "fanduel_props.sqlite"
BAK = HERE / "fanduel_props.bak.sqlite"
KEEP_DAYS = 45

if not DB.exists():
    raise SystemExit("no DB — nothing to maintain")

con = sqlite3.connect(DB)
cut = (dt.datetime.utcnow() - dt.timedelta(days=KEEP_DAYS)).isoformat()
n_old = con.execute("SELECT COUNT(*) FROM fd_lines WHERE collected_at < ?", (cut,)).fetchone()[0]
if n_old:
    con.execute("DELETE FROM fd_lines WHERE collected_at < ?", (cut,))
    con.commit()
    con.execute("VACUUM")
tmp = BAK.with_suffix(".tmp")
if tmp.exists():
    tmp.unlink()
con.execute("VACUUM INTO ?", (str(tmp),))
con.close()
os.replace(tmp, BAK)
print(f"fd_maintain: pruned {n_old} rows older than {KEEP_DAYS}d · backup "
      f"{BAK.stat().st_size / 1e6:.0f}MB · db {DB.stat().st_size / 1e6:.0f}MB")
