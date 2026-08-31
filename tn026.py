#!/usr/bin/env python3
"""Diagnose the implausible rest_days / load_14 effects before believing them.

t = -73 on rest_days and a 0.14 log-loss improvement over a SHARP CLOSING PRICE are not findings;
a gain that size would be worth a fortune and would not have survived in a 4.7%-hold market.

PRIME SUSPECT: TML stamps `tourney_date`, the tournament START, on EVERY round. So all of a
player's matches in one event share a date. That makes
    rest_days  = days since the last TOURNAMENT, which is 0 for both players from round 2 onward
    load_14    = matches already played in THIS tournament, i.e. how many rounds a player has
                 already WON here
The second is the dangerous one: it is a proxy for "is currently winning this event", which is
mechanically correlated with quality in a way the raw feature does not disclose.

CHECKS:
  1. what do these features actually look like - distribution, and share of exact zeros
  2. is the effect there in FIRST-ROUND matches only, where no within-tournament history exists?
     If it vanishes, it is a within-tournament artifact, not a fatigue or freshness signal.
"""
import math
import re
import sqlite3
import statistics as st
import unicodedata
from collections import defaultdict, deque
from datetime import date as DT
from pathlib import Path

DB = Path(__file__).resolve().parent / "tennis_ace.sqlite"


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", s.lower()).strip()


def ktml(n):
    p = [x for x in norm(n).split() if x]
    return "%s|%s" % (" ".join(p[1:]), p[0][:1]) if len(p) >= 2 else None


con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=60)
M = con.execute("""SELECT date, year, surface, player, opp, round FROM ace_pm
                   WHERE won=1 AND surface IS NOT NULL AND surface!='' ORDER BY date""").fetchall()
oh = defaultdict(list)
for d, wk, lk, wo, lo in con.execute("SELECT date, wkey, lkey, w_odds, l_odds FROM odds_hist"):
    oh[(wk, lk)].append((d, wo, lo))
con.close()


def shin2(o1, o2):
    q = [1.0 / o1, 1.0 / o2]
    R = sum(q)
    lo, hi = 0.0, 0.99
    for _ in range(120):
        z = 0.5 * (lo + hi)
        s = sum((math.sqrt(z * z + 4 * (1 - z) * x * x / R) - z) / (2 * (1 - z)) for x in q)
        if s > 1.0:
            lo = z
        else:
            hi = z
    z = 0.5 * (lo + hi)
    p = [(math.sqrt(z * z + 4 * (1 - z) * x * x / R) - z) / (2 * (1 - z)) for x in q]
    return p[0] / sum(p)


def price(d, w, l):
    kw, kl = ktml(w), ktml(l)
    if not kw or not kl:
        return None
    for dd, wo, lo in oh.get((kw, kl), []):
        try:
            if abs((DT.fromisoformat(dd) - DT.fromisoformat(d)).days) <= 4:
                return shin2(wo, lo)
        except Exception:                                               # noqa: BLE001
            continue
    return None


lastdate, recent = {}, defaultdict(list)
rows = []
for d, yr, surf, w, l, rnd in M:
    p = price(d, w, l)
    if p is not None and 0.01 < p < 0.99:
        def rest(pl):
            return min((DT.fromisoformat(d) - DT.fromisoformat(lastdate[pl])).days, 30) \
                if pl in lastdate else None

        def load(pl):
            return sum(1 for x in recent[pl]
                       if (DT.fromisoformat(d) - DT.fromisoformat(x)).days <= 14)
        rw, rl = rest(w), rest(l)
        rows.append((yr, p, (rw - rl) if (rw is not None and rl is not None) else None,
                     load(w) - load(l), str(rnd)))
    lastdate[w] = d
    lastdate[l] = d
    recent[w].append(d)
    recent[l].append(d)

print("priced matches: %d" % len(rows))
rd = [r[2] for r in rows if r[2] is not None]
ld = [r[3] for r in rows]
print()
print("rest_days difference: zeros %.1f%%  mean %+.2f  sd %.2f  range %d..%d"
      % (100.0 * sum(1 for x in rd if x == 0) / len(rd), st.mean(rd), st.pstdev(rd),
         min(rd), max(rd)))
print("load_14   difference: zeros %.1f%%  mean %+.2f  sd %.2f  range %d..%d"
      % (100.0 * sum(1 for x in ld if x == 0) / len(ld), st.mean(ld), st.pstdev(ld),
         min(ld), max(ld)))
print()
print("MEAN FEATURE VALUE, winner minus loser — a nonzero mean IS the leak, because the rows are")
print("winner-oriented and an unbiased feature should average zero:")
print("   rest_days %+.3f   load_14 %+.3f" % (st.mean(rd), st.mean(ld)))
print()
byr = defaultdict(list)
for yr, p, r_, l_, rnd in rows:
    byr[str(rnd)].append((r_, l_))
print("by round (mean winner-minus-loser):")
for rnd in sorted(byr, key=lambda k: -len(byr[k]))[:8]:
    v = byr[rnd]
    rr = [x[0] for x in v if x[0] is not None]
    ll_ = [x[1] for x in v]
    print("   %-8s n=%5d  rest %+7.3f  load %+7.3f"
          % (rnd[:8], len(v), st.mean(rr) if rr else 0, st.mean(ll_)))
print()
print("READ: if load_14 is systematically POSITIVE for winners, it is encoding 'already winning")
print("this tournament' rather than fatigue, and its predictive power is circular.")
