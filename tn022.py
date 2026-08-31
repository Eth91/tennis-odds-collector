#!/usr/bin/env python3
"""Diagnose the +45% set-winner "edge". A number that large is a bug, not an opportunity.

Rule from the golf phase: when an effect is unexpectedly huge, audit the data before believing it.
A mean EV of +0.45 implies fair x odds = 1.45. FanDuel prices a set-winner favourite near 1.26,
which would require a fair probability above 1.1 - impossible. So either the derived fair is wrong,
or the FanDuel runner is being matched to the wrong side of the Pinnacle quote.

This prints every input for a handful of matches so the failure is visible rather than inferred.
"""
import math
import re
import sqlite3
import unicodedata
from collections import defaultdict
from datetime import datetime as D
from pathlib import Path

HERE = Path(__file__).resolve().parent


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", s.lower()).strip()


def surn(n):
    p = [x for x in norm(n).split() if x]
    return p[-1] if p else ""


def pk(a, b):
    return tuple(sorted([surn(a), surn(b)]))


def tsd(a, b):
    try:
        return abs((D.fromisoformat(a[:19]) - D.fromisoformat(b[:19])).total_seconds()) / 60.0
    except Exception:                                                   # noqa: BLE001
        return 1e9


def shin2(o1, o2):
    q = [1.0 / o1, 1.0 / o2]
    R = sum(q)
    lo, hi = 0.0, 0.99
    for _ in range(160):
        z = 0.5 * (lo + hi)
        s = sum((math.sqrt(z * z + 4 * (1 - z) * x * x / R) - z) / (2 * (1 - z)) for x in q)
        if s > 1.0:
            lo = z
        else:
            hi = z
    z = 0.5 * (lo + hi)
    p = [(math.sqrt(z * z + 4 * (1 - z) * x * x / R) - z) / (2 * (1 - z)) for x in q]
    t = sum(p)
    return p[0] / t, p[1] / t


fd = sqlite3.connect("file:%s?mode=ro" % (HERE / "tennis_fd.sqlite"), uri=True, timeout=60)
pn = sqlite3.connect("file:%s?mode=ro" % (HERE / "odds.sqlite"), uri=True, timeout=60)

print("=" * 90)
print("WHAT IS PINNACLE'S SET SPREAD, ACTUALLY? (assumed: -1.5 = wins 2-0)")
print("=" * 90)
for r in pn.execute("""SELECT p1, p2, ml1, ml2, set_spread, spr_home, spr_away, set_total_line,
                              set_over, set_under FROM odds
                       WHERE set_spread IS NOT NULL AND spr_home IS NOT NULL
                         AND collected_at >= '2026-08-30' LIMIT 5"""):
    p1, p2, a, b, ssp, sh, sa, stl, so, su = r
    m1, m2 = shin2(a, b)
    h, aw = shin2(sh, sa)
    s_un, s_ov = shin2(su, so)
    print("   %-22s vs %-22s" % (str(p1)[:22], str(p2)[:22]))
    print("      moneyline %.2f/%.2f -> M(p1)=%.3f" % (a, b, m1))
    print("      set_spread=%s  spr %.2f/%.2f -> shin %.3f/%.3f" % (ssp, sh, sa, h, aw))
    print("      set_total=%s   o/u %.2f/%.2f -> P(straights)=%.3f" % (stl, so, su, s_un))
    print("      IF spr_home were P(p1 wins 2-0) it must be <= P(straights)=%.3f and <= M=%.3f"
          % (s_un, m1))
    print("         -> %s" % ("CONSISTENT" if h <= min(s_un, m1) + 0.02 else
                              "IMPOSSIBLE: spr_home %.3f exceeds that bound, so it is NOT "
                              "P(wins 2-0)" % h))
    print()

print("=" * 90)
print("FANDUEL 1st-SET PRICES vs the derived fair — three worked examples")
print("=" * 90)
F = fd.execute("""SELECT event_name, best_of, start_time, runner_name, odds, collected_at
                  FROM fd_tennis WHERE market_type='TO_WIN_1ST_SET'""").fetchall()
Praw = pn.execute("""SELECT p1,p2,start_time,collected_at,ml1,ml2,set_total_line,set_over,
                            set_under,set_spread,spr_home,spr_away FROM odds
                     WHERE collected_at >= '2026-08-29'""").fetchall()
fd.close()
pn.close()
P = defaultdict(list)
for r in Praw:
    P[(pk(r[0], r[1]), str(r[2])[:10])].append(r)
shown = 0
for ev, bo, stt, rn, od, ts in F:
    parts = str(ev).split(" v ")
    if len(parts) != 2 or int(bo or 3) != 3:
        continue
    cand = P.get((pk(parts[0], parts[1]), str(stt)[:10]))
    if not cand:
        continue
    c = min(cand, key=lambda x: tsd(str(x[3]), ts))
    if tsd(str(c[3]), ts) > 25 or not c[10] or not c[7]:
        continue
    m1, m2 = shin2(c[4], c[5])
    s_un, _ = shin2(c[8], c[7])
    a_h, a_a = shin2(c[10], c[11])
    same = surn(rn) == surn(c[0])
    M = m1 if same else m2
    a = a_h if same else a_a
    fair = a + (1 - s_un) / 2
    print("   %-38s runner=%-20s FD odds %.2f" % (str(ev)[:38], str(rn)[:20], od))
    print("      M=%.3f  P(straights)=%.3f  spr side=%.3f  ->  derived fair=%.3f  EV=%+.3f"
          % (M, s_un, a, fair, fair * od - 1))
    print("      sanity: a set-winner probability must sit BETWEEN 0.5 and M for a favourite;")
    print("              %.3f vs M=%.3f -> %s" % (fair, M,
          "plausible" if abs(fair - M) < 0.25 else "IMPLAUSIBLE, the derivation is wrong"))
    print()
    shown += 1
    if shown >= 3:
        break
