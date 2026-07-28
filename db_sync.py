"""Text-artifact transport for the WNBA state DBs — replaces committing binaries.

WHY (two reasons, the second is the serious one):

1. BLOAT. `wnba_ledger.sqlite` (176K) has 2,578 commits, `wnba_proj_log` 1,511, `wnba_clv`
   1,272. Binaries don't delta, so every run stores a fresh full copy; .git is 1.0 GB.

2. SILENT DATA LOSS. Two writers touch the ledger — the VM loop and the `nightly-digest`
   Action — and nightly-digest resolves with `git pull --rebase -X theirs`. On a BINARY that
   takes one side's whole file, so whichever writer loses the race has its grading silently
   discarded. Sorted JSONL merges line-wise instead, and `--build` unions by primary key, so
   neither writer can clobber the other.

Format: data/<db>/<table>.jsonl — one JSON ARRAY per line in the column order recorded in
that dir's schema.sql. Rows are emitted in a stable sort so a run APPENDS rather than
reshuffles (small deltas); never change a sort key casually.

    python db_sync.py --export     # DBs -> data/*/
    python db_sync.py --build      # data/*/ -> DBs, UNIONing into an existing DB by PK
    python db_sync.py --verify     # rebuild to temp DBs and hash-compare
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

DBS = {
    "wnba_ledger.sqlite": {
        "data": HERE / "data" / "wnba_ledger",
        "sort": {"predictions": "pred_date, player, stat, line",
                 "parlays": "pred_date, key",
                 "selections": "pred_date, team, player, stat"},
    },
    "wnba_proj_log.sqlite": {
        "data": HERE / "data" / "wnba_proj_log",
        "sort": {"projections": "date, player, stat"},
    },
    "wnba_clv.sqlite": {
        "data": HERE / "data" / "wnba_clv",
        "sort": {},
    },
}


def tables(con):
    return [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]


def cols(con, t):
    return [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]


def _sel(c):
    return ",".join('"' + x + '"' for x in c)


def _order(con, t, cfg):
    """Configured sort, falling back to every column so output is always deterministic."""
    o = cfg["sort"].get(t)
    if not o:
        return _sel(cols(con, t))
    have = set(cols(con, t))
    parts = [p.strip() for p in o.split(",")]
    return o if all(p in have for p in parts) else _sel(cols(con, t))


def export_one(name, cfg):
    db = HERE / name
    if not db.exists():
        print(f"  ({name} absent — skipped)")
        return 0
    cfg["data"].mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    ddl = []
    for t in tables(con):
        for (sql,) in con.execute(
                "SELECT sql FROM sqlite_master WHERE type IN ('table','index') "
                "AND tbl_name=? AND sql IS NOT NULL", (t,)):
            ddl.append(sql.strip() + ";")
    (cfg["data"] / "schema.sql").write_text("\n".join(ddl) + "\n")
    total = 0
    for t in tables(con):
        c = cols(con, t)
        n = 0
        with (cfg["data"] / f"{t}.jsonl").open("w") as fh:
            for row in con.execute(f'SELECT {_sel(c)} FROM "{t}" ORDER BY {_order(con, t, cfg)}'):
                fh.write(json.dumps(list(row), separators=(",", ":"), ensure_ascii=False) + "\n")
                n += 1
        total += n
        print(f"  {name:<22} {t:<14} {n:>6} rows")
    con.close()
    return total


def build_one(name, cfg, target=None):
    """Restore/union artifacts into the DB.

    Unlike a plain restore this MERGES: existing rows stay, artifact rows are INSERT-OR-IGNOREd
    by primary key. So a runner that already has a DB (or a second writer that graded rows the
    artifacts predate) never loses work — the failure mode `-X theirs` on a binary caused.
    """
    target = Path(target) if target else HERE / name
    schema = cfg["data"] / "schema.sql"
    if not schema.exists():
        print(f"  {name}: no artifacts, skipping")
        return 0
    fresh = not target.exists() or target.stat().st_size == 0
    con = sqlite3.connect(target)
    con.executescript(schema.read_text())          # CREATE TABLE IF NOT EXISTS — safe on both
    total = 0
    for f in sorted(cfg["data"].glob("*.jsonl")):
        t = f.stem
        c = cols(con, t)
        if not c:
            continue
        ins = (f'INSERT OR IGNORE INTO "{t}" ({_sel(c)}) '
               f'VALUES ({",".join("?" * len(c))})')
        batch = []
        with f.open() as fh:
            for line in fh:
                line = line.strip()
                if line:
                    batch.append(json.loads(line))
                if len(batch) >= 4000:
                    con.executemany(ins, batch)
                    batch.clear()
            if batch:
                con.executemany(ins, batch)
        n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        total += n
        print(f"  {target.name:<22} {t:<14} {n:>6} rows ({'built' if fresh else 'merged'})")
    con.commit()
    con.close()
    return total


def verify_one(name, cfg):
    db = HERE / name
    if not db.exists():
        return True
    tmp = Path(tempfile.mkdtemp()) / name
    build_one(name, cfg, target=tmp)
    a = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    b = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
    ok = True
    for t in tables(a):
        c = cols(a, t)
        o = _order(a, t, cfg)

        def h(con):
            d, n = hashlib.sha256(), 0
            for row in con.execute(f'SELECT {_sel(c)} FROM "{t}" ORDER BY {o}'):
                d.update(json.dumps(list(row), separators=(",", ":"),
                                    ensure_ascii=False).encode())
                n += 1
            return d.digest(), n
        ha, na = h(a)
        hb, nb = h(b)
        same = ha == hb and na == nb
        ok &= same
        print(f"  {name:<22} {t:<14} orig {na:>6} | rebuilt {nb:>6} | "
              f"{'MATCH' if same else '*** MISMATCH ***'}")
    a.close()
    b.close()
    tmp.unlink(missing_ok=True)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    if a.export:
        print("exported", sum(export_one(n, c) for n, c in DBS.items()), "rows")
    elif a.build:
        print("restored", sum(build_one(n, c) for n, c in DBS.items()), "rows")
    elif a.verify:
        ok = all([verify_one(n, c) for n, c in DBS.items()])
        print("\nROUND-TRIP", "OK" if ok else "FAILED")
        sys.exit(0 if ok else 1)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
