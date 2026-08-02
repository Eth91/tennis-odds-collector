"""Grade both sides of every correlation-cap contest, using the ESPN game-log cache.

Fixes two flaws in the first pass: wnba_gamelogs.sqlite is empty (logs live in the ESPN disk cache
reached via wnba_wowy.game_log), and the breadcrumb re-logs the same contest on every scan, so 2245
rows are far fewer real contests — dedupe to (date, team, kept, capped, stat, line) keeping the last
seen odds/ev, which is the state closest to tip.

WNBA is FROZEN. Nothing here ships; this is a hypothesis measured against the frozen baseline.
"""
import csv
import os
from collections import defaultdict

import wnba_wowy as W

CAP = "wnba_capped_legs.csv"
seen = {}
with open(CAP) as f:
    for r in csv.reader(f):
        if len(r) < 9:
            continue
        try:
            k = (r[0], r[1], r[2], r[3], r[4], float(r[5]))
            seen[k] = {"date": r[0], "team": r[1], "kept": r[2], "capped": r[3], "stat": r[4],
                       "line": float(r[5]), "odds": float(r[6] or 0), "ev": float(r[7] or 0),
                       "d_min": float(r[8]) if r[8] not in ("", "None") else None}
        except ValueError:
            continue
rows = list(seen.values())
print("  raw breadcrumb rows -> %d DISTINCT contests over %d dates"
      % (len(rows), len({r["date"] for r in rows})))

ids = W.roster_ids() or {}
_log = {}


def glog(name):
    if name not in _log:
        pid = ids.get(name)
        try:
            _log[name] = W.game_log(pid) if pid else []
        except Exception:
            _log[name] = []
    return _log[name]


def actual(name, date, stat):
    for g in glog(name):
        if (g.get("date") or "")[:10] != date[:10]:
            continue
        p, rb, a = g.get("pts"), g.get("reb"), g.get("ast")
        if p is None:
            return None
        return {"points": p, "rebounds": rb, "assists": a,
                "pra": (p or 0) + (rb or 0) + (a or 0),
                "pts_reb": (p or 0) + (rb or 0), "pts_ast": (p or 0) + (a or 0),
                "reb_ast": (rb or 0) + (a or 0)}.get(stat)
    return None


import sqlite3
led = sqlite3.connect("wnba_ledger.sqlite")
led.row_factory = sqlite3.Row


def kept_row(date, team, player, stat):
    r = led.execute("SELECT * FROM predictions WHERE pred_date=? AND team=? AND player=? "
                    "AND side='over' ORDER BY ev DESC LIMIT 1", (date, team, player)).fetchone()
    return dict(r) if r else None


def aband(x):
    return 0 if (x is not None and 3 <= x <= 8) else 1


tally = defaultdict(lambda: [0, 0])
detail, ungraded = [], 0
for r in rows:
    kr = kept_row(r["date"], r["team"], r["kept"], r["stat"])
    if not kr:
        ungraded += 1
        continue
    ka = actual(r["kept"], r["date"], kr.get("stat") or r["stat"])
    ca = actual(r["capped"], r["date"], r["stat"])
    if ka is None or ca is None:
        ungraded += 1
        continue
    kres = 1 if ka > (kr.get("line") or 0) else 0
    cres = 1 if ca > r["line"] else 0
    if kres == cres:
        continue                                   # non-discriminating
    kdm, cdm = kr.get("d_min"), r["d_min"]
    tally["CURRENT (shadow-band, odds, ev)"][0 if kres else 1] += 1
    pick_kept = (aband(kdm), float(kr.get("odds") or 99), -(kr.get("ev") or 0)) <= \
                (aband(cdm), r["odds"], -r["ev"])
    tally["A-BAND FIRST (3-8, odds, ev)"][0 if (kres if pick_kept else cres) else 1] += 1
    pk_ev = (kr.get("ev") or 0) >= r["ev"]
    tally["PURE EV"][0 if (kres if pk_ev else cres) else 1] += 1
    pk_od = float(kr.get("odds") or 99) <= r["odds"]
    tally["PURE ODDS (favorite)"][0 if (kres if pk_od else cres) else 1] += 1
    detail.append((r["date"], r["team"], r["stat"], r["kept"], kdm, kres,
                   r["capped"], cdm, cres, pick_kept))

print("  ungraded/unmatched contests skipped: %d" % ungraded)
print("\n=== DISCRIMINATING contests (the two legs disagreed): %d ===" % len(detail))
print("  %-11s %-4s %-8s %-24s %-24s %s"
      % ("date", "tm", "stat", "KEPT (d_min) res", "CAPPED (d_min) res", "A-band would keep"))
for d in detail:
    print("  %-11s %-4s %-8s %-24s %-24s %s"
          % (d[0], d[1], d[2],
             "%s (%s) %s" % (d[3][:11], d[4], "W" if d[5] else "L"),
             "%s (%s) %s" % (d[6][:11], d[7], "W" if d[8] else "L"),
             "kept" if d[9] else "CAPPED"))

print("\n=== which keep-rule picks the winning leg more often? ===")
print("  %-38s %6s %6s %8s" % ("rule", "right", "wrong", "acc"))
for k in ("CURRENT (shadow-band, odds, ev)", "A-BAND FIRST (3-8, odds, ev)",
          "PURE ODDS (favorite)", "PURE EV"):
    a, b = tally[k]
    n = a + b
    print("  %-38s %6d %6d %7.1f%%" % (k, a, b, 100 * a / n if n else 0))
print("\n  Only DISCRIMINATING contests count — where both legs won or both lost, the keep-rule")
print("  made no difference and including them would dilute the signal toward 50%.")
