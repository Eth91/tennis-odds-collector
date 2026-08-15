#!/usr/bin/env python3
"""GM-012 — is BIRDIE MAKING a skill distinct from scoring, and is it distinct BY PAR TYPE?

Birdies are the only production-relevant market with a positive historical record, so the birdie
model deserves scrutiny rather than assumption. birdie_rounds carries something no other table
has: holes played AND birdies made, separately for par 3s, 4s and 5s, over 49,854 player-rounds.
That is a real decomposition of scoring, at ROUND level, with honest timestamps -- unlike sg_stats,
which is a season aggregate and had to be lagged a whole year.

THE ORDER MATTERS, and it is the order that killed strokes-gained. SG failed not because the
categories were unmeasurable but because their PARTIALS were ~0: once you knew SG_TOT, knowing
SG_OTT added nothing. The same trap is available here, so the questions are asked in the order
that can kill the idea cheapest:

  LEG 1  Is birdie-making a skill at all beyond the score rating? A player who scores well makes
         birdies; the question is whether birdie rate carries information the RATING does not.
  LEG 2  Are par-3 / par-4 / par-5 birdie rates DISTINCT skills? Concretely: does a player's
         par-5 birdie rate predict their FUTURE par-5 birdie rate once their OVERALL birdie rate
         is known? If the partial is ~0, there is one birdie skill wearing three labels, and no
         "par-5 specialist x par-5-heavy course" interaction can exist.
  LEG 3  Only if LEG 2 survives: does course par-5 opportunity x player par-5 skill predict?

Everything is split chronologically -- earlier half estimates, later half tests -- and the
between-player variance is decomposed against sampling noise, because three separate
"some players are better at X" hypotheses have already turned out to be 92-100% noise here.

2026 IS THE PROTECTED HOLDOUT AND IS NOT READ.
"""
import re
import sqlite3
from collections import defaultdict

import numpy as np

import pga_ruler as RU

pm = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
br = pm.execute("SELECT tid, tname, player, rnd, p3h, p3b, p4h, p4b, p5h, p5b "
                "FROM birdie_rounds").fetchall()
ev_dates = {}
for evn, d in pm.execute("SELECT event, MIN(date) FROM rounds GROUP BY event"):
    ev_dates[" ".join(str(evn).lower().split())] = str(d)
pm.close()
print("birdie rows %d" % len(br))


def yr(tid):
    m = re.match(r"R(\d{4})", str(tid))
    return int(m.group(1)) if m else None


D = []
for tid, tname, pl, rnd, p3h, p3b, p4h, p4b, p5h, p5b in br:
    y = yr(tid)
    if y is None or y >= 2026:
        continue
    h = [(3, p3h or 0, p3b or 0), (4, p4h or 0, p4b or 0), (5, p5h or 0, p5b or 0)]
    tot_h = sum(x[1] for x in h)
    tot_b = sum(x[2] for x in h)
    if tot_h < 15:                                   # a partial round, not a full 18
        continue
    D.append(dict(tid=tid, yr=y, pl=RU.norm(pl), rnd=int(rnd), h=h,
                  tot_h=tot_h, tot_b=tot_b))
print("usable player-rounds %d (2023-2025) | players %d | events %d"
      % (len(D), len({d["pl"] for d in D}), len({d["tid"] for d in D})))
print("years: %s" % dict((y, sum(1 for d in D if d["yr"] == y)) for y in (2024, 2025)))

# field-relative birdie rate per (tid, rnd): removes course and conditions
bykey = defaultdict(list)
for d in D:
    bykey[(d["tid"], d["rnd"])].append(d)
for k, v in bykey.items():
    for par in (3, 4, 5):
        num = sum(x["h"][par - 3][2] for x in v)
        den = sum(x["h"][par - 3][1] for x in v)
        rate = num / den if den else 0.0
        for x in v:
            x.setdefault("exp", {})[par] = rate * x["h"][par - 3][1]
    tb = sum(x["tot_b"] for x in v)
    th = sum(x["tot_h"] for x in v)
    r = tb / th if th else 0.0
    for x in v:
        x["exp_tot"] = r * x["tot_h"]

print("\n" + "=" * 94)
print("LEG 1 — is birdie-making persistent at all, above the field?")
print("=" * 94)
per = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
for d in D:
    half = "early" if d["yr"] <= 2024 else "late"
    per[d["pl"]][half][0] += d["tot_b"]
    per[d["pl"]][half][1] += d["exp_tot"]
both = [p for p, v in per.items()
        if v["early"][1] >= 60 and v["late"][1] >= 60]
print("   players with >=60 expected birdies in BOTH halves: %d" % len(both))
a = np.array([per[p]["early"][0] - per[p]["early"][1] for p in both])
b = np.array([per[p]["late"][0] - per[p]["late"][1] for p in both])
na = np.array([per[p]["early"][1] for p in both])
nb = np.array([per[p]["late"][1] for p in both])
ra = a / na
rb = b / nb
print("   corr(birdies above field, early vs late) = %+.3f" % float(np.corrcoef(ra, rb)[0, 1]))
noise = float(np.mean(1.0 / na))
obs = float(ra.var(ddof=1))
print("   observed variance %.6f | Poisson sampling noise %.6f | TRUE %.6f"
      % (obs, noise, max(obs - noise, 0.0)))
print("   -> %.0f%% of the spread is real skill" % (100 * max(obs - noise, 0.0) / obs
                                                   if obs > 0 else 0))

print("\n" + "=" * 94)
print("LEG 2 — are par-3/4/5 birdie rates DISTINCT skills, or one skill in three costumes?")
print("=" * 94)
pp = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0.0, 0.0])))
for d in D:
    half = "early" if d["yr"] <= 2024 else "late"
    for par in (3, 4, 5):
        pp[d["pl"]][half][par][0] += d["h"][par - 3][2]
        pp[d["pl"]][half][par][1] += d["exp"][par]
qual = [p for p in pp
        if all(pp[p][h][par][1] >= 20 for h in ("early", "late") for par in (3, 4, 5))]
print("   players qualifying on all three par types in both halves: %d" % len(qual))
if len(qual) >= 40:
    print("\n   %-6s %14s %14s %16s" % ("par", "raw corr", "partial corr", "verdict"))
    tot_e = np.array([sum(pp[p]["early"][x][0] - pp[p]["early"][x][1] for x in (3, 4, 5))
                      / sum(pp[p]["early"][x][1] for x in (3, 4, 5)) for p in qual])
    tot_l = np.array([sum(pp[p]["late"][x][0] - pp[p]["late"][x][1] for x in (3, 4, 5))
                      / sum(pp[p]["late"][x][1] for x in (3, 4, 5)) for p in qual])
    for par in (3, 4, 5):
        e = np.array([(pp[p]["early"][par][0] - pp[p]["early"][par][1])
                      / pp[p]["early"][par][1] for p in qual])
        lt = np.array([(pp[p]["late"][par][0] - pp[p]["late"][par][1])
                       / pp[p]["late"][par][1] for p in qual])
        raw = float(np.corrcoef(e, lt)[0, 1])
        # partial: remove OVERALL early rate from both sides
        def resid(x, ctrl):
            A = np.column_stack([np.ones(len(ctrl)), ctrl])
            return x - A @ np.linalg.lstsq(A, x, rcond=None)[0]
        pr = float(np.corrcoef(resid(e, tot_e), resid(lt, tot_e))[0, 1])
        print("   par %-2d %14.3f %14.3f %16s"
              % (par, raw, pr,
                 "DISTINCT" if pr > 0.15 else "not distinct"))
    print("\n   raw = does this par-type rate repeat at all")
    print("   partial = does it repeat ONCE the player's OVERALL birdie rate is known")
    print("   A partial near zero means one birdie skill wearing three labels -- exactly what")
    print("   killed strokes-gained (OTT +0.001, APP +0.016, PUTT -0.044 once SG_TOT was known).")
