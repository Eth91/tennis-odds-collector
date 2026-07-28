"""Ingest lines_delta.json (Actions' per-run MLB/WNBA line rows) into fanduel_props.sqlite.

2026-07-25 postmortem part 2: Actions could not push the 100MB fanduel_props.sqlite blob
(three-writer war; 10-try retry loop still lost). Fix = Actions commits ONLY a small
lines_delta.json (its own run's rows, ~100-500KB — pushes never lose); this script runs on
the VM each loop cycle and INSERTs rows newer than the local watermark per (sport, book).
The big DB now has a single committer (the VM). Idempotent; gated on exported_at marker.
"""
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = [(HERE / "lines_delta.json", Path("/tmp/.lines_ingest_actions")),
           (HERE / "lines_delta_mac.json", Path("/tmp/.lines_ingest_mac"))]

con = None
for src, gate in SOURCES:
    if not src.exists():
        continue
    try:
        d = json.loads(src.read_text())
    except (ValueError, OSError):
        continue
    stamp = d.get("exported_at") or ""
    if gate.exists() and gate.read_text().strip() == stamp:
        continue
    rows = d.get("rows") or []
    if con is None:
        con = sqlite3.connect(HERE / "fanduel_props.sqlite")
        con.execute("PRAGMA busy_timeout=60000")
        # SELF-HEAL (2026-07-28): this queries fd_lines directly, so an EMPTY or missing DB
        # was a hard crash EVERY loop cycle -- which is exactly what happened when the file
        # got zeroed during git surgery: ~2h of "no such table: fd_lines" spam that would
        # have masked a real failure. Creating the table makes a lost DB self-repair and
        # simply resume collecting.
        con.execute("""CREATE TABLE IF NOT EXISTS fd_lines (
        collected_at TEXT, sport TEXT, event TEXT, player TEXT, stat TEXT, line REAL,
        side TEXT, odds REAL, book TEXT DEFAULT 'fd',
        PRIMARY KEY (collected_at, sport, player, stat, line, side))""")
    wm = {}
    ins = 0
    for r in rows:
        # row = [collected_at, sport, event, player, stat, line, side, odds, book]
        if len(r) != 9:
            continue
        key = (r[1], r[8])
        if key not in wm:
            wm[key] = con.execute("SELECT COALESCE(MAX(collected_at),'') FROM fd_lines "
                                  "WHERE sport=? AND book=?", key).fetchone()[0]
        if r[0] > wm[key]:
            con.execute("INSERT INTO fd_lines (collected_at, sport, event, player, stat, line, "
                        "side, odds, book) VALUES (?,?,?,?,?,?,?,?,?)", r)
            ins += 1
    con.commit()
    gate.write_text(stamp)
    if ins:
        print(f"lines_ingest: +{ins} rows from {src.name} {stamp}")
if con is not None:
    con.close()
