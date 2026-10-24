"""Print fd_quotes rows fetched after --since as JSON lines, for the Mac to pull over ssh.

    python3 export.py --since 2026-10-24T00:00:00+00:00
"""
import argparse
import json
import sqlite3
import sys

DB = "/home/ubuntu/ncaaf-prekick/data/ncaaf_fd_prices.sqlite"

ap = argparse.ArgumentParser()
ap.add_argument("--since", default="")
a = ap.parse_args()
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
cols = [r[1] for r in con.execute("PRAGMA table_info(fd_quotes)")]
print(json.dumps({"columns": cols}))
for row in con.execute("SELECT * FROM fd_quotes WHERE fetched_at > ? ORDER BY fetched_at", (a.since,)):
    sys.stdout.write(json.dumps(row) + "\n")
