#!/usr/bin/env python3
"""GM-015 — is the "week effect" actually RATING ERROR? The test my coupling hypothesis failed to be.

THE CONTRADICTION. GM-007/008 measured the within-event round-to-round residual correlation at
+0.0954 on the cleanest sample available (R1->R2, full field, zero selection), stable in every year,
placebo p=0.000, agreed by two functional forms and by five of six round pairs. GM-010 then
substituted that value for the shipped RHO=0.050 and every placement calibration slope got worse.
GM-014 tested my explanation -- that rho and SPREAD are a jointly-fitted pair -- by re-tuning
SPREAD at each rho. BOTH rhos picked SPREAD=1.30, and 0.085 still lost head-to-head (+0.00097).
So the coupling story is refuted and the contradiction is still open.

THE REMAINING EXPLANATION. The residual being correlated is

    resid = (score - that round's field mean) - as-of rating

and it contains TWO things, not one:
    a genuine week effect   -- the player is sharp or off THIS WEEK. This is what RHO models.
    RATING ERROR            -- the rating is simply wrong for this player right now (stale, thin
                               record, mid-career change). This makes ALL of that player's
                               residuals correlated, this week and every other week.
The simulator already prices rating error, through K_SHRINK and each player's sigma. If the
+0.0954 is mostly rating error, then feeding it back in as rho DOUBLE-COUNTS it, which would
widen the 72-hole distribution that was already the right width -- exactly the symptom GM-010 saw.

THE TEST, and it is decisive because the two components have different reach:
    WITHIN  event: corr(round i, round j) for the same player in the SAME event    -> week + rating
    ACROSS  events: corr(round in event A, round in event B), same player, same season, DIFFERENT
            weeks                                                                  -> rating only
A week effect cannot survive into a different week. So:
    ACROSS ~ 0        -> the correlation really is a week effect, and the contradiction is elsewhere
    ACROSS ~ WITHIN   -> there is no week effect to speak of; it is rating error wearing that name,
                         RHO is already right at ~0.05, and GM-007's headline needs retracting

Single ROUND pairs on both sides, never averages, so the two numbers are directly comparable --
averaging reduces noise and would inflate the within-event side on its own.
2026 IS THE PROTECTED HOLDOUT AND IS NOT READ.
"""
import hashlib
import math
import pickle
import sqlite3
from collections import defaultdict

import numpy as np

import pga_ruler as RU

KEY = hashlib.sha1(("%s|%s|%s|%s" % (RU.HALF_LIFE_D, RU.K_SHRINK, RU.SIG_SHRINK,
                                     RU.MIN_ROUNDS)).encode()).hexdigest()[:12]
fits = pickle.load(open("ratings_cache_%s.pkl" % KEY, "rb"))
fd = sorted(fits)


def rf(d):
    lo, hi = 0, len(fd)
    while lo < hi:
        m = (lo + hi) // 2
        if fd[m] < d:
            lo = m + 1
        else:
            hi = m
    return fits[fd[lo - 1]] if lo > 0 else None


con = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
rows = con.execute("SELECT event_id, event, date, player, rnd, score FROM rounds "
                   "WHERE date < '2026-01-01' ORDER BY date").fetchall()
con.close()
ev = defaultdict(lambda: defaultdict(dict))
em = {}
for eid, evn, d, pl, rnd, sc in rows:
    if sc is None:
        continue
    ev[eid][int(rnd)][pl] = float(sc)
    em[eid] = (str(evn), str(d))

res = defaultdict(dict)                      # (eid, rnd) -> player -> residual
for eid, byr in ev.items():
    R = rf(em[eid][1])
    if not R:
        continue
    for rnd, sc in byr.items():
        if len(sc) < 40:
            continue
        m = float(np.mean(list(sc.values())))
        for pl, s in sc.items():
            r = R.get(RU.norm(pl)) or R.get(pl)
            if r is not None:
                res[(eid, rnd)][pl] = (s - m) - float(r[0])
print("event-rounds with residuals: %d" % len(res))

# player -> [(date, eid, rnd, resid)] in time order
byp = defaultdict(list)
for (eid, rnd), d in res.items():
    for pl, v in d.items():
        byp[pl].append((em[eid][1], eid, rnd, v))
for pl in byp:
    byp[pl].sort()


def report(pairs, label):
    if len(pairs) < 300:
        print("   %-46s too few (%d)" % (label, len(pairs)))
        return None
    x = np.array([p[0] for p in pairs])
    y = np.array([p[1] for p in pairs])
    g = [p[2] for p in pairs]
    r = float(np.corrcoef(x, y)[0, 1])
    bl = defaultdict(list)
    for a, b, k in pairs:
        bl[k].append((a, b))
    rs = [float(np.corrcoef([t[0] for t in v], [t[1] for t in v])[0, 1])
          for v in bl.values() if len(v) >= 30
          and np.std([t[0] for t in v]) > 1e-9 and np.std([t[1] for t in v]) > 1e-9]
    se = (np.std(rs, ddof=1) / math.sqrt(len(rs))) if len(rs) > 2 else float("nan")
    print("   %-46s corr %+.4f   n=%6d   clusters %3d   SE %.4f"
          % (label, r, len(x), len(rs), se))
    return r


print("\n" + "=" * 96)
print("WITHIN one event vs ACROSS different events — same player, single rounds both sides")
print("=" * 96)

within = []
for pl, v in byp.items():
    bye = defaultdict(list)
    for dt_, eid, rnd, r in v:
        bye[eid].append((rnd, r))
    for eid, lst in bye.items():
        if 1 in [x[0] for x in lst] and 2 in [x[0] for x in lst]:
            a = [x[1] for x in lst if x[0] == 1][0]
            b = [x[1] for x in lst if x[0] == 2][0]
            within.append((a, b, eid))
w = report(within, "WITHIN event: R1 vs R2 (week effect + rating error)")

# ACROSS: this player's R1 in one event vs their R1 in the NEXT event they played
across = []
gap_days = []
import datetime as dt
for pl, v in byp.items():
    firsts = {}
    for dt_, eid, rnd, r in v:
        if rnd == 1 and eid not in firsts:
            firsts[eid] = (dt_, r)
    seq = sorted(firsts.items(), key=lambda kv: kv[1][0])
    for i in range(len(seq) - 1):
        (e1, (d1, r1)), (e2, (d2, r2)) = seq[i], seq[i + 1]
        if e1 == e2:
            continue
        across.append((r1, r2, e1))
        try:
            gap_days.append((dt.date.fromisoformat(d2[:10])
                             - dt.date.fromisoformat(d1[:10])).days)
        except Exception:                                               # noqa: BLE001
            pass
a = report(across, "ACROSS events: R1 vs R1 of the NEXT event (rating error only)")
if gap_days:
    print("      median gap between those two events: %d days" % int(np.median(gap_days)))

# and a longer reach: R1 vs R1 two events later
across2 = []
for pl, v in byp.items():
    firsts = {}
    for dt_, eid, rnd, r in v:
        if rnd == 1 and eid not in firsts:
            firsts[eid] = (dt_, r)
    seq = sorted(firsts.items(), key=lambda kv: kv[1][0])
    for i in range(len(seq) - 2):
        (e1, (d1, r1)), (e3, (d3, r3)) = seq[i], seq[i + 2]
        across2.append((r1, r3, e1))
report(across2, "ACROSS events: R1 vs R1 TWO events later")

print("\n" + "=" * 96)
print("VERDICT")
print("=" * 96)
if w is not None and a is not None:
    print("   within  %+.4f      across %+.4f      ratio across/within = %.2f" % (w, a, a / w if w else 0))
    if a >= 0.6 * w:
        print("   -> The correlation REACHES INTO OTHER WEEKS almost as strongly as within one.")
        print("      That cannot be a week effect. It is RATING ERROR, which the simulator already")
        print("      prices through K_SHRINK and sigma. Feeding it back as RHO double-counts it,")
        print("      which is exactly why GM-010 and GM-014 got worse probabilities.")
        print("      GM-007's headline -- 'RHO should be 0.085' -- IS RETRACTED.")
    elif a <= 0.25 * w:
        print("   -> The correlation is confined to the week. It IS a week effect, RHO really is")
        print("      understated, and the reason substituting it fails lies somewhere else.")
    else:
        print("   -> Mixed: part week effect, part rating error. RHO is overstated by the rating-")
        print("      error share, which is roughly %.0f%% of the measured value." % (100 * a / w))
