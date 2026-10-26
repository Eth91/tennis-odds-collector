#!/usr/bin/env python3
"""TN-023 — SET WINNERS done honestly: partial identification, not a fabricated point estimate.

TN-021 reported a +45% set-winner edge. It was my bug. The derivation used Pinnacle's spr_home as
P(wins 2-0), and that is provably not what it is: Krueger's moneyline implies M=0.169 while
spr_home reads 0.400, and no player wins 2-0 more often than they win the match. The spread values
sit near 0.4-0.6 on every match, which is a handicap line set to be near coin-flip.

WHAT IS ACTUALLY IDENTIFIED. From the moneyline and the set total alone:
    M = a + b        (a = P(A 2-0), b = P(A 2-1))
    S = a + d        (d = P(B 2-0))
    a + b + c + d = 1
gives P(A wins set 1) = a + (1-S)/2 - but `a` is NOT pinned down. It is BOUNDED:
    max(0, M+S-1) <= a <= min(M, S)
so the set-winner probability lies in an interval, not at a point. That is the same lesson as
"top N and ties is not point-identified" from the golf phase: when a quantity is only partially
identified, the honest object is the RANGE, and a point estimate invents information.

TEST: does FanDuel's implied probability fall INSIDE the sharp-implied interval? If yes, no edge is
demonstrable - the sharp markets simply do not pin the number tightly enough to prove one. If
FanDuel sits OUTSIDE the whole interval, that is a real disagreement no choice of `a` can explain.
"""
import math
import re
import sqlite3
import statistics as st
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
F = fd.execute("""SELECT event_name, best_of, start_time, market_type, runner_name, odds,
                         collected_at FROM fd_tennis
                  WHERE market_type IN ('TO_WIN_1ST_SET','SET_2_WINNER')""").fetchall()
Praw = pn.execute("""SELECT p1,p2,start_time,collected_at,ml1,ml2,set_total_line,set_over,set_under
                     FROM odds WHERE collected_at >= '2026-08-29' AND ml1 IS NOT NULL""").fetchall()
fd.close()
pn.close()
P = defaultdict(list)
for r in Praw:
    P[(pk(r[0], r[1]), str(r[2])[:10])].append(r)

inside = outside_hi = outside_lo = 0
best_ev = []
for ev, bo, stt, mt, rn, od, ts in F:
    parts = str(ev).split(" v ")
    if len(parts) != 2 or int(bo or 3) != 3:
        continue
    cand = P.get((pk(parts[0], parts[1]), str(stt)[:10]))
    if not cand:
        continue
    c = min(cand, key=lambda x: tsd(str(x[3]), ts))
    if tsd(str(c[3]), ts) > 25 or not c[7] or not c[8] or not c[6]:
        continue
    if abs(float(c[6]) - 2.5) > 1e-6:
        continue
    m1, m2 = shin2(c[4], c[5])
    s_un, _s_ov = shin2(c[8], c[7])          # under 2.5 = straights
    same = surn(rn) == surn(c[0])
    M = m1 if same else m2
    S = s_un
    a_lo = max(0.0, M + S - 1.0)
    a_hi = min(M, S)
    lo = a_lo + (1 - S) / 2
    hi = a_hi + (1 - S) / 2
    imp = 1.0 / od                            # FanDuel implied, vig INCLUDED
    if imp < lo:
        outside_lo += 1
        best_ev.append((lo * od - 1, ev, rn, od, lo, hi, imp))
    elif imp > hi:
        outside_hi += 1
    else:
        inside += 1

tot = inside + outside_hi + outside_lo
print("=" * 90)
print("SET WINNERS — is FanDuel outside the SHARP-IMPLIED INTERVAL?")
print("=" * 90)
print("   best-of-3 quotes compared: %d" % tot)
if tot:
    print("   FanDuel implied INSIDE the interval      : %d (%.1f%%)  -> no edge demonstrable"
          % (inside, 100.0 * inside / tot))
    print("   FanDuel implied ABOVE the interval       : %d (%.1f%%)  -> FD too SHORT, we would "
          "want the other side, which FanDuel does not offer separately"
          % (outside_hi, 100.0 * outside_hi / tot))
    print("   FanDuel implied BELOW the interval       : %d (%.1f%%)  -> FD generous, POSSIBLE EDGE"
          % (outside_lo, 100.0 * outside_lo / tot))
    print()
    print("   NOTE the asymmetry: FanDuel's implied probability contains its vig, so it should sit")
    print("   ABOVE a fair number by construction. Landing inside or above proves nothing.")
    if best_ev:
        print("\n   quotes BELOW the whole interval (the only ones that could be +EV):")
        for e, ev, rn, od, lo, hi, imp in sorted(best_ev, key=lambda z: -z[0])[:8]:
            print("      %-34s %-20s odds %.2f  implied %.3f vs interval [%.3f, %.3f]  EV>=%+.3f"
                  % (str(ev)[:34], str(rn)[:20], od, imp, lo, hi, e))
        evs = [x[0] for x in best_ev]
        print("\n   n=%d  mean minimum EV %+.4f  median %+.4f"
              % (len(evs), st.mean(evs), st.median(evs)))
    else:
        print("\n   NO quote fell below the interval. Set winners show no demonstrable edge.")
