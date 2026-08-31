#!/usr/bin/env python3
"""TN-019 — does the +EV longshot tail survive a SHIN de-vig? The golf trap, re-run in tennis.

TN-018 found 17 of 166 FanDuel moneyline quotes paying more than Pinnacle's fair probability, mean
+6.0%, and EVERY ONE a longshot (mean fair prob 0.173, odds 7.8-15.0). Before believing that, it
has to survive the exact trap EXP-015 identified in the golf phase.

Pinnacle's fair number came from PROPORTIONAL de-vigging, which splits the margin evenly across
both sides. Real books do not: the favourite-longshot bias means the margin sits disproportionately
on the longshot. Under proportional de-vig a longshot's fair probability is therefore too HIGH -
and since EV = fair * odds - 1, an inflated fair probability manufactures a positive EV out of
nothing. A longshot-only tail is precisely the signature that would produce.

    proportional   p_i = q_i / sum(q)                        margin split evenly
    Shin           solves for an insider fraction z, moving margin ONTO the longshot

If the tail is real it survives Shin. If it is a de-vig artifact it collapses, and the honest
answer to "is there an edge on the moneyline" is no.

EXP-015 measured this in golf: proportional put the favourite end 12 points too dear and the
longshot end 142 points too cheap. Two-way tennis markets are far less extreme, but the DIRECTION
is the same and the tail here sits entirely at the end the bias distorts.
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


def shin_two(o1, o2):
    """Shin de-vig for a two-way book. Returns (p1, p2, z)."""
    q = [1.0 / o1, 1.0 / o2]
    R = sum(q)
    lo, hi = 0.0, 0.99
    for _ in range(200):
        z = 0.5 * (lo + hi)
        s = sum((math.sqrt(z * z + 4 * (1 - z) * x * x / R) - z) / (2 * (1 - z)) for x in q)
        if s > 1.0:
            lo = z
        else:
            hi = z
    z = 0.5 * (lo + hi)
    p = [(math.sqrt(z * z + 4 * (1 - z) * x * x / R) - z) / (2 * (1 - z)) for x in q]
    t = sum(p)
    return p[0] / t, p[1] / t, z


fd = sqlite3.connect("file:%s?mode=ro" % (HERE / "tennis_fd.sqlite"), uri=True, timeout=60)
pn = sqlite3.connect("file:%s?mode=ro" % (HERE / "odds.sqlite"), uri=True, timeout=60)
fdrows = fd.execute("""SELECT event_name, tour, start_time, runner_name, odds, collected_at
                       FROM fd_tennis WHERE market_type='MATCH_BETTING'""").fetchall()
pnrows = pn.execute("""SELECT p1, p2, start_time, collected_at, ml1, ml2 FROM odds
                       WHERE collected_at >= '2026-08-30' AND ml1 IS NOT NULL""").fetchall()
fd.close()
pn.close()
P = defaultdict(list)
for p1, p2, stt, ts, a, b in pnrows:
    P[(pk(p1, p2), str(stt)[:10])].append((str(ts), p1, a, b))

recs = []
for ev, tour, stt, rn, od, ts in fdrows:
    parts = str(ev).split(" v ")
    if len(parts) != 2:
        continue
    cand = P.get((pk(parts[0], parts[1]), str(stt)[:10]))
    if not cand:
        continue
    c = min(cand, key=lambda x: tsd(x[0], ts))
    if tsd(c[0], ts) > 20 or not c[2] or not c[3]:
        continue
    same = surn(rn) == surn(c[1])
    po, qo = (c[2], c[3]) if same else (c[3], c[2])
    prop = (1 / po) / ((1 / po) + (1 / qo))
    s1, s2, z = shin_two(po, qo)
    shin = s1
    recs.append(dict(ev=ev, rn=rn, tour=tour, od=od, prop=prop, shin=shin, z=z,
                     ev_prop=prop * od - 1, ev_shin=shin * od - 1))
# dedupe to latest quote per (match, runner)
best = {}
for r in recs:
    best[(r["ev"], r["rn"])] = r
recs = list(best.values())
print("moneyline quotes paired with a simultaneous Pinnacle price: %d" % len(recs))
print("mean Shin insider fraction z = %.4f" % st.mean([r["z"] for r in recs]))
print()
print("=" * 92)
print("DOES THE +EV TAIL SURVIVE SHIN?")
print("=" * 92)
for lbl, key in (("proportional de-vig", "ev_prop"), ("SHIN de-vig", "ev_shin")):
    v = [r[key] for r in recs]
    pos = [x for x in v if x > 0]
    print("   %-22s mean EV %+.4f | +EV quotes %d of %d (%.1f%%) | mean +EV %.4f | max %.4f"
          % (lbl, st.mean(v), len(pos), len(v), 100.0 * len(pos) / len(v),
             st.mean(pos) if pos else 0.0, max(v)))
print()
print("   by sharp-fair probability band (Shin), which is where the tail lived:")
print("   %-18s %6s %14s %14s" % ("band", "n", "EV proportional", "EV Shin"))
for lo, hi, lab in ((0.0, 0.15, "deep longshot <.15"), (0.15, 0.30, "longshot .15-.30"),
                    (0.30, 0.50, "dog      .30-.50"), (0.50, 0.75, "fav      .50-.75"),
                    (0.75, 1.01, "heavy fav  >.75")):
    s = [r for r in recs if lo <= r["shin"] < hi]
    if len(s) >= 8:
        print("   %-18s %6d %+14.4f %+14.4f"
              % (lab, len(s), st.mean([r["ev_prop"] for r in s]),
                 st.mean([r["ev_shin"] for r in s])))
print()
pp = sum(1 for r in recs if r["ev_prop"] > 0)
ps = sum(1 for r in recs if r["ev_shin"] > 0)
print("   +EV count: %d under proportional  ->  %d under Shin" % (pp, ps))
if ps <= 0.4 * max(pp, 1):
    print("   -> THE TAIL LARGELY COLLAPSES. It was substantially a de-vig artifact, exactly the")
    print("      failure mode EXP-015 found in golf. No moneyline edge is demonstrated.")
elif ps >= 0.8 * max(pp, 1):
    print("   -> THE TAIL SURVIVES. FanDuel genuinely pays over sharp-fair on these longshots.")
else:
    print("   -> PARTIALLY survives; the honest count is the Shin one.")
