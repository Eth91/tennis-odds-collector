#!/usr/bin/env python3
"""Durable TIMESTAMPED price archive for repricing research (§8, §36).

WHY A SECOND ARCHIVE. research/line_archive.sqlite keeps ONE row per (day,player,stat,line,side)
-- the last pre-game quote. That is fine for base rates and USELESS here: repricing research
needs the price at each timestamp, which that collapse destroys. This preserves every distinct
observation.

DEDUP ACROSS OVERLAPPING BACKUPS. Each daily backup is itself a ~3-day window, so consecutive
backups re-observe the same rows. PRIMARY KEY (d,player,stat,line,side,book,collected_at) makes
re-ingest idempotent -- the same observation seen in three backups is stored once. Without it the
series would look 3x denser and every "time to reprice" would be wrong.

NO RECONSTRUCTION. Only prices actually observed at a timestamp are stored. Nothing is
interpolated, forward-filled, or inferred from a final state (§8, §36)."""
import gzip, shutil, sqlite3, sys, tempfile
from pathlib import Path

BK = Path("/home/ubuntu/backups/wnba")
LIVE = Path("/home/ubuntu/tennis-odds-collector/wnba_lines.sqlite")
OUT = Path("/home/ubuntu/tennis-odds-collector/research/tick_archive.sqlite")

out = sqlite3.connect(OUT, timeout=180)
out.execute("PRAGMA journal_mode=WAL")
out.execute("PRAGMA synchronous=OFF")
out.execute("""CREATE TABLE IF NOT EXISTS obs(
    d TEXT, player TEXT, stat TEXT, line REAL, side TEXT, book TEXT,
    collected_at TEXT, odds REAL,
    PRIMARY KEY(d, player, stat, line, side, book, collected_at))""")

SEL = ("SELECT substr(collected_at,1,10), player, stat, line, side, book, collected_at, odds "
       "FROM fd_lines WHERE sport='wnba' AND (live IS NULL OR live=0) AND odds IS NOT NULL "
       "AND line IS NOT NULL AND stat IN ('points','rebounds','assists')")

def ingest(path, label):
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=180)
    before = out.execute("SELECT COUNT(*) FROM obs").fetchone()[0]
    n = 0
    batch = []
    for row in src.execute(SEL):
        batch.append(row); n += 1
        if len(batch) >= 50000:
            out.executemany("INSERT OR IGNORE INTO obs VALUES(?,?,?,?,?,?,?,?)", batch)
            batch.clear()
    if batch:
        out.executemany("INSERT OR IGNORE INTO obs VALUES(?,?,?,?,?,?,?,?)", batch)
    out.commit(); src.close()
    after = out.execute("SELECT COUNT(*) FROM obs").fetchone()[0]
    print(f"  {label:10s} scanned {n:8d}  NEW {after-before:8d}  (dup {n-(after-before):8d})  "
          f"total {after:9d}", flush=True)

files = sorted(BK.glob("wnba_lines.*.sqlite.gz"))
print(f"{len(files)} backup(s) + live", flush=True)
tmpd = tempfile.mkdtemp(prefix="tick_")
try:
    for f in files:
        tmp = Path(tmpd) / "b.sqlite"
        with gzip.open(f, "rb") as fi, open(tmp, "wb") as fo:
            shutil.copyfileobj(fi, fo, 1 << 22)
        try:
            ingest(tmp, f.name.split(".")[1])
        except Exception as e:                                        # noqa: BLE001
            print(f"  {f.name}: FAILED {str(e)[:70]} -- SKIPPED, not counted as empty", flush=True)
        finally:
            tmp.unlink(missing_ok=True)
    ingest(LIVE, "live")
finally:
    shutil.rmtree(tmpd, ignore_errors=True)

print("\nindexing...", flush=True)
for ddl in ("CREATE INDEX IF NOT EXISTS i_key ON obs(player, stat, line, side, collected_at)",
            "CREATE INDEX IF NOT EXISTS i_day ON obs(d, collected_at)",
            "CREATE INDEX IF NOT EXISTS i_ps  ON obs(d, player, stat)"):
    out.execute(ddl)
out.commit()

print("\n=== §37 DATABASE VALIDATION ===", flush=True)
q = out.execute
print("  rows                :", q("SELECT COUNT(*) FROM obs").fetchone()[0])
print("  oldest / newest     :", q("SELECT MIN(collected_at),MAX(collected_at) FROM obs").fetchone())
print("  distinct dates      :", q("SELECT COUNT(DISTINCT d) FROM obs").fetchone()[0])
print("  distinct players    :", q("SELECT COUNT(DISTINCT player) FROM obs").fetchone()[0])
print("  distinct books      :", q("SELECT book, COUNT(*) FROM obs GROUP BY book").fetchall())
print("  distinct stats      :", q("SELECT stat, COUNT(*) FROM obs GROUP BY stat").fetchall())
print("\n  rows + snapshots per day (snapshots = distinct collected_at):")
for d, n, snaps, ps in q("SELECT d, COUNT(*), COUNT(DISTINCT collected_at), "
                         "COUNT(DISTINCT player||'|'||stat) FROM obs GROUP BY d ORDER BY d"):
    print(f"    {d}  rows {n:8d}  snapshots {snaps:5d}  player-stats {ps:4d}")
out.close()
