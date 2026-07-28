"""Row-merge origin's fanduel_props.sqlite (FETCH_HEAD blob) into the local DB.

Fixes the two-writer blob war (2026-07-25 postmortem): Actions snapshots MLB/WNBA lines
every ~30min while the VM loop commits its own copy of the same 100MB binary every ~2min.
Git can only pick ONE blob per race — and the VM's pull (-X theirs) keeps the VM's copy —
so Actions' fresh rows kept vanishing (18h repo-wide MLB line freeze; K/OUTS-COMPASS
starved at line lookup). This merge makes the race harmless: before the VM's next commit,
any NEW rows in origin's blob (per sport+book watermark) are INSERTed locally, so the VM's
committed blob is a superset and convergence no longer depends on who wins the push race.

Sha-gated: one `git ls-tree` per cycle; the 100MB blob extraction runs only when the blob
actually changed (~every 30min when Actions lands a snapshot).
"""
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = Path("/tmp/.fd_merge_sha")
TMP = Path("/tmp/fd_origin.sqlite")

try:
    parts = subprocess.run(["git", "ls-tree", "FETCH_HEAD", "--", "fanduel_props.sqlite"],
                           cwd=HERE, capture_output=True, text=True, timeout=30).stdout.split()
    sha = parts[2] if len(parts) >= 3 else None
except Exception:
    sha = None
if not sha:
    sys.exit(0)
if GATE.exists() and GATE.read_text().strip() == sha:
    sys.exit(0)

try:
    with open(TMP, "wb") as f:
        r = subprocess.run(["git", "cat-file", "blob", sha], cwd=HERE, stdout=f, timeout=180)
    if r.returncode != 0:
        sys.exit(0)
    con = sqlite3.connect(HERE / "fanduel_props.sqlite")
    con.execute("PRAGMA busy_timeout=60000")
    con.execute("ATTACH ? AS o", (str(TMP),))
    # fanduel_props.sqlite was UNTRACKED 2026-07-28 (blob war: 117MB > GitHub's 100MB limit),
    # so the committed blob this merges from may be empty or absent. That is expected, not an
    # error -- exit quietly rather than raising "no such table: o.fd_lines" every cycle.
    # NOTE: must query the ATTACHED db's schema (o.sqlite_master), not the main one -- the
    # main DB always has fd_lines, so checking it passed the guard and still blew up on
    # o.fd_lines (caught in deploy verification).
    if not con.execute("SELECT name FROM o.sqlite_master WHERE type='table' "
                       "AND name='fd_lines'").fetchone():
        con.close()
        TMP.unlink(missing_ok=True)
        sys.exit(0)
    con.execute("""CREATE TABLE IF NOT EXISTS fd_lines (
        collected_at TEXT, sport TEXT, event TEXT, player TEXT, stat TEXT, line REAL,
        side TEXT, odds REAL, book TEXT DEFAULT 'fd',
        PRIMARY KEY (collected_at, sport, player, stat, line, side))""")
    ins = 0
    for sport, book in con.execute("SELECT DISTINCT sport, book FROM o.fd_lines").fetchall():
        wm = con.execute("SELECT COALESCE(MAX(collected_at),'') FROM fd_lines "
                         "WHERE sport=? AND book=?", (sport, book)).fetchone()[0]
        cur = con.execute("INSERT INTO fd_lines SELECT * FROM o.fd_lines "
                          "WHERE sport=? AND book=? AND collected_at > ?", (sport, book, wm))
        ins += cur.rowcount
    con.commit()
    con.close()
    GATE.write_text(sha)
    if ins:
        print(f"fd_merge: +{ins} rows from origin snapshot {sha[:8]}")
finally:
    TMP.unlink(missing_ok=True)
