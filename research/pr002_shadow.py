#!/usr/bin/env python3
"""PR-002 SHADOW ARM — capture stint-WOWY candidates at T-8h..T-13h, prospectively.

WHY. EXP-013 found the decay curve is monotone across 8 leads and that book coverage is
99.5-100% from 8-12h out, where the model is still UNDER-confident. That was discovered
retrospectively on an archive, on n=17-19 per arm, with the 2026-only cells much weaker
(+2.4% at 12h). PR-002 can therefore only be earned FORWARD, and forward evidence needs a
capture path that does not exist yet: production evaluates near tip.

WHAT THIS IS NOT. It writes to its own DB, never to `predictions`. It never pings. It never
consumes a TOP-2 slot. Nothing here is imported by any production module. v1.8 is untouched.

⚠️ ONE ROW PER (game, player, stat, line, lead-bucket). Without that key the cron would log the
same candidate every 30 minutes and the sample would look 20x larger than it is -- the same
duplicate-flag failure that once inflated a TT record to "133-17".

⚠️ PRICE IS CAPTURED AT LOG TIME, NOT AT GRADING. The whole hypothesis is that the price at
T-8h..T-12h differs from the price at tip. Re-reading the price later would destroy the only
thing being measured.
"""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
DB = HERE / "pr002_shadow.sqlite"
LEAD_LO, LEAD_HI = 7.0, 13.0          # the window PR-002 is about
BUCKETS = ((11.0, 13.0, "t12"), (9.0, 11.0, "t10"), (7.0, 9.0, "t8"))


def _db():
    c = sqlite3.connect(DB, timeout=60)
    c.execute("PRAGMA busy_timeout=60000")
    c.execute("""CREATE TABLE IF NOT EXISTS shadow(
        slate TEXT, event TEXT, player TEXT, stat TEXT, line REAL, side TEXT,
        price REAL, book TEXT, bucket TEXT, hrs_to_tip REAL,
        out_player TEXT, p_over REAL, ev REAL, proj REAL, rate36 REAL, off_min REAL,
        n_without INTEGER, logged_at TEXT, actual REAL, result TEXT, graded INTEGER DEFAULT 0,
        PRIMARY KEY(slate, player, stat, line, bucket))""")
    return c


def capture():
    import wnba_tonight as T
    import wnba_wowy as W
    import wnba_stint_wowy as SW

    now = dt.datetime.now(dt.timezone.utc)
    try:
        tips = T.tip_times()
    except Exception as e:                                           # noqa: BLE001
        print(f"tip_times failed: {str(e)[:60]}"); return 0
    if not tips:
        print("no slate"); return 0

    # which teams are inside the capture window right now?
    live = {}
    for team, when in tips.items():
        try:
            t = when if isinstance(when, dt.datetime) else dt.datetime.fromisoformat(str(when))
            if t.tzinfo is None:
                t = t.replace(tzinfo=dt.timezone.utc)
            hrs = (t - now).total_seconds() / 3600.0
        except Exception:                                            # noqa: BLE001
            continue
        if LEAD_LO <= hrs <= LEAD_HI:
            live[team] = hrs
    if not live:
        print("no team inside the 7-13h window"); return 0

    inj = T.injuries()
    pl = W.players()
    outs_by = {}
    for n, st in inj.items():
        p = pl.get(n)
        if p and "out" in str(st).lower() and (p.get("min", 0) >= 15):
            outs_by.setdefault(p["team"], []).append(n)

    src = sqlite3.connect(f"file:{ROOT/'wnba_stints.sqlite'}?mode=ro", uri=True, timeout=30)
    mem = sqlite3.connect(":memory:")
    src.backup(mem); src.close()
    for ddl in ("CREATE INDEX i1 ON onfloor(player, game_date)",
                "CREATE INDEX i3 ON pairs(player, mate, game_date)"):
        try: mem.execute(ddl)
        except Exception: pass                                       # noqa: BLE001
    mem.row_factory = sqlite3.Row

    slate = dt.datetime.now(dt.timezone(dt.timedelta(hours=-4))).date().isoformat()
    con = _db()
    wrote = 0
    for team, hrs in live.items():
        bucket = next((b for lo, hi, b in BUCKETS if lo <= hrs < hi), None)
        if not bucket or team not in outs_by:
            continue
        for outp in outs_by[team]:
            omp = (pl.get(outp) or {}).get("min", 0)
            mates = [n for n, v in pl.items()
                     if v.get("team") == team and n != outp and (v.get("gp") or 0) >= 5]
            starters = SW.projected_starters(mem, mates, slate, outs=outs_by[team])
            for ben in mates:
                if ben not in starters:
                    continue                                  # PR-002 inherits the starter gate
                nwo, _, _ = SW.game_level_n_without(mem, ben, outp, slate)
                if nwo >= 2:
                    continue                                  # production already covers this
                try:
                    props = T.posted_props(ben) or {}
                except Exception:                                    # noqa: BLE001
                    continue
                for stat in ("rebounds", "assists", "points"):
                    for line, pr in (props.get(stat) or {}).items():
                        dec = pr[0] if isinstance(pr, (list, tuple)) else pr
                        if not dec or not (1.3 <= float(dec) <= 6.0):
                            continue
                        p_mkt = None
                        if isinstance(pr, (list, tuple)) and len(pr) > 1 and pr[1]:
                            po, pu = 1.0 / float(dec), 1.0 / float(pr[1])
                            p_mkt = po / (po + pu)
                        est = SW.project(mem, ben, outp, stat, float(line), slate, omp,
                                         p_market=p_mkt)
                        if not est:
                            continue
                        ev = est["p_over"] * float(dec) - 1.0
                        if ev < 0.0:
                            continue
                        try:
                            con.execute(
                                "INSERT OR IGNORE INTO shadow(slate,event,player,stat,line,side,"
                                "price,book,bucket,hrs_to_tip,out_player,p_over,ev,proj,rate36,"
                                "off_min,n_without,logged_at) VALUES(?,?,?,?,?,'over',?,'fd',?,?,"
                                "?,?,?,?,?,?,?,?)",
                                (slate, team, ben, stat, float(line), float(dec), bucket,
                                 round(hrs, 2), outp, est["p_over"], ev, est["proj"],
                                 est["rate36"], est["off_min"], nwo, now.isoformat()))
                            wrote += con.total_changes and 1 or 0
                        except Exception:                            # noqa: BLE001
                            pass
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM shadow").fetchone()[0]
    con.close()
    print(f"PR-002 shadow: {len(live)} team(s) in window; table now {n} rows")
    return n


def grade():
    """Fill results from the box score. Same fail-closed rule as production: never grade off an
    incomplete box, because absence from a partial parse is a failed fetch, not a DNP."""
    import wnba_ledger as L
    con = _db()
    rows = con.execute("SELECT rowid,slate,player,stat,line FROM shadow WHERE graded=0").fetchall()
    done = 0
    for rid, slate, player, stat, line in rows:
        if slate >= dt.date.today().isoformat():
            continue
        box = L.box_actuals(slate)
        if not box or not L.box_complete(slate):
            continue
        hit = next((v for k, v in box.items() if player.lower() in str(k).lower()), None)
        if hit is None:
            continue
        act = hit.get(stat)
        if act is None:
            continue
        con.execute("UPDATE shadow SET actual=?, result=?, graded=1 WHERE rowid=?",
                    (act, "over" if act > line else "under", rid))
        done += 1
    con.commit(); con.close()
    print(f"PR-002 shadow: graded {done}")
    return done


if __name__ == "__main__":
    if "--grade" in sys.argv:
        grade()
    else:
        capture()
        grade()
