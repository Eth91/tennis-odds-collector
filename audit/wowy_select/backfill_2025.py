"""Rebuild 2025-26's lineups (nba_onoff.parse) on the Mac from cdn.nba.com play-by-play, starters from the 11/3 VM
backup of nba_matchup (read-only). Output: onoff_2025.sqlite here. Read-only for every live store."""
import sqlite3, sys, time
sys.path.insert(0, "/Users/ethandown/nba-engine")
import nba_onoff as O
M = "/Users/ethandown/nba-engine-proj/.projdata/vm_backup_20261103/nba_matchup.20261103.sqlite"
mcon = sqlite3.connect(f"file:{M}?mode=ro", uri=True)
con = O.connect("onoff_2025.sqlite")
t = time.time()
print(O.fetch(con, mcon, "2025-26", workers=4, today="2026-11-06"), f"{time.time() - t:.0f}s", flush=True)
print(con.execute("SELECT COUNT(*), SUM(ok) FROM games").fetchone(), flush=True)
