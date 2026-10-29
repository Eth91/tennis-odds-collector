#!/usr/bin/env python3
"""Reconstruct a WNBA line archive from the daily backups.

WHY THIS HAS TO EXIST. `wnba_lines.sqlite` is a 3-DAY ROLLING BUFFER -- 1.5M rows spanning
2026-08-13..08-15 only. Two experiments (EXP-023/024) were built on it as if it were a month of
history and produced a confident, entirely invalid base rate. Each daily backup is itself a
3-day window, so the UNION of the backups is the only real line history that will ever exist.

One row per (date, player, stat, line, side): the LAST pre-game quote. Research-only; writes to
research/line_archive.sqlite and is imported by nothing in production."""
import gzip, os, shutil, sqlite3, subprocess, sys, tempfile
from pathlib import Path

BK = Path("/home/ubuntu/backups/wnba")
LIVE = Path("/home/ubuntu/tennis-odds-collector/wnba_lines.sqlite")
OUT = Path("/home/ubuntu/tennis-odds-collector/research/line_archive.sqlite")
STATS = ("points", "rebounds", "assists")

out = sqlite3.connect(OUT, timeout=120)
out.execute("PRAGMA journal_mode=WAL")
out.execute("""CREATE TABLE IF NOT EXISTS q(
    d TEXT, player TEXT, stat TEXT, line REAL, side TEXT, odds REAL, book TEXT,
    collected_at TEXT, PRIMARY KEY(d, player, stat, line, side))""")

Q = ("SELECT substr(collected_at,1,10) d, player, stat, line, side, odds, book, "
     "MAX(collected_at) ca FROM fd_lines WHERE sport='wnba' AND (live IS NULL OR live=0) "
     "AND odds IS NOT NULL AND line IS NOT NULL AND stat IN ('points','rebounds','assists') "
     "GROUP BY d, player, stat, line, side")

def ingest(path, label):
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=120)
    n = ins = 0
    for d, player, stat, line, side, odds, book, ca in src.execute(Q):
        n += 1
        cur = out.execute("SELECT collected_at FROM q WHERE d=? AND player=? AND stat=? "
                          "AND line=? AND side=?", (d, player, stat, line, side)).fetchone()
        if cur is None or str(ca) > str(cur[0]):
            out.execute("INSERT OR REPLACE INTO q VALUES(?,?,?,?,?,?,?,?)",
                        (d, player, stat, line, side, odds, book, ca))
            ins += 1
    src.close(); out.commit()
    tot = out.execute("SELECT COUNT(*) FROM q").fetchone()[0]
    days = out.execute("SELECT COUNT(DISTINCT d) FROM q").fetchone()[0]
    print(f"  {label:14s} read {n:7d}  new/updated {ins:7d}  archive now {tot:7d} rows / {days} days",
          flush=True)

files = sorted(BK.glob("wnba_lines.*.sqlite.gz"))
print(f"{len(files)} backup(s) + live DB", flush=True)
tmpd = tempfile.mkdtemp(prefix="linearch_")
try:
    for f in files:
        tmp = Path(tmpd) / "b.sqlite"
        with gzip.open(f, "rb") as fi, open(tmp, "wb") as fo:
            shutil.copyfileobj(fi, fo, 1 << 22)
        try:
            ingest(tmp, f.name.split(".")[1])
        except Exception as e:                                        # noqa: BLE001
            print(f"  {f.name}: FAILED {str(e)[:70]} -- skipped, NOT counted as empty", flush=True)
        finally:
            tmp.unlink(missing_ok=True)
    ingest(LIVE, "live")
finally:
    shutil.rmtree(tmpd, ignore_errors=True)

print("\nper-day coverage (distinct player-stat combos -- a real slate is 60-150):", flush=True)
for d, c, pc in out.execute("SELECT d, COUNT(*), COUNT(DISTINCT player||'|'||stat) FROM q "
                            "GROUP BY d ORDER BY d"):
    print(f"  {d}  rows {c:6d}  player-stats {pc:4d}", flush=True)
out.close()
