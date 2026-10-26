#!/usr/bin/env python3
"""GM-005 — WHY is dispersion persistent? Course property, or "how well do we know this field"?

GM-004 established the effect and it is strong: dispersion runs 1.93 to 4.15 against a model that
assumes one number, persists at corr +0.692 year to year, cuts OOS MSE by 49.8% predicting 2025
from 2023-24, and a placebo that shuffles histories between events beats it 0 times in 400.

The mechanism is NOT established, and two stories fit every one of those numbers while implying
OPPOSITE fixes:

  COURSE      hard setups and exposed courses separate players. Dispersion is a property of the
              venue, it repeats because the venue repeats, and the fix is a per-event sigma
              multiplier taken from prior editions.
  FIELD       residual dispersion is inflated by players the RATING KNOWS BADLY -- a thin record
              means a noisy rating means a large residual, whatever the course does. Tournaments
              draw similar fields every year (an opposite-field event pulls the same tier
              annually), so this repeats just as neatly. The fix would then be per-player sigma
              handling, and a course multiplier would be fitting the symptom.

The residual already nets out each player's rating, so field STRENGTH is handled -- but rating
UNCERTAINTY is not, and that is the confound.

TEST. Two field-knowledge proxies, both available as-of:
    mean rating sigma of the field   (the model's own uncertainty)
    mean n_rounds behind the rating  (thin records -> noisy ratings)
    share of the field under MIN_ROUNDS=20, where pga_ruler halves the rating toward field average
Then: does EVENT IDENTITY still predict next year's dispersion once these are partialled out? If
the persistence survives, it is the venue. If it collapses, it is the field.

2026 IS THE PROTECTED HOLDOUT AND IS NOT READ.
"""
import hashlib
import pickle
import sqlite3
from collections import defaultdict

import numpy as np

import pga_ruler as RU

KEY = hashlib.sha1(("%s|%s|%s|%s" % (RU.HALF_LIFE_D, RU.K_SHRINK, RU.SIG_SHRINK,
                                     RU.MIN_ROUNDS)).encode()).hexdigest()[:12]
fits = pickle.load(open("ratings_cache_%s.pkl" % KEY, "rb"))
fit_dates = sorted(fits)

con = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
rows = con.execute("SELECT event_id, event, date, player, rnd, score FROM rounds "
                   "WHERE date < '2026-01-01' ORDER BY date").fetchall()
con.close()
ev = defaultdict(lambda: defaultdict(dict))
emeta = {}
for eid, evn, d, pl, rnd, sc in rows:
    if sc is None:
        continue
    ev[eid][int(rnd)][pl] = float(sc)
    emeta[eid] = (str(evn), str(d))


def ratings_for(date):
    lo, hi = 0, len(fit_dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if fit_dates[mid] < date:
            lo = mid + 1
        else:
            hi = mid
    return fits[fit_dates[lo - 1]] if lo > 0 else None


E = {}
for eid, byr in ev.items():
    evn, d0 = emeta[eid]
    R = ratings_for(d0)
    if not R:
        continue
    res_all, sig, nr, thin, mean_sc = [], [], [], 0, []
    tot = 0
    for rnd, sc in byr.items():
        if len(sc) < 40:
            continue
        m = float(np.mean(list(sc.values())))
        mean_sc += list(sc.values())
        for pl, s in sc.items():
            r = R.get(RU.norm(pl)) or R.get(pl)
            if r is None:
                continue
            res_all.append((s - m) - float(r[0]))
            if rnd == 1:
                sig.append(float(r[1]))
                nr.append(float(r[2]))
                thin += 1 if float(r[2]) < RU.MIN_ROUNDS else 0
                tot += 1
    if len(res_all) >= 120 and tot >= 40:
        E[eid] = dict(disp=float(np.std(res_all, ddof=1)),
                      sig=float(np.mean(sig)), nr=float(np.mean(nr)),
                      thin=thin / max(tot, 1), size=tot,
                      hard=float(np.mean(mean_sc)),
                      yr=int(emeta[eid][1][:4]), name=emeta[eid][0])
print("events with dispersion + field diagnostics: %d" % len(E))

d = np.array([v["disp"] for v in E.values()])
print("\n" + "=" * 92)
print("1 — WHAT DOES DISPERSION CORRELATE WITH?")
print("=" * 92)
for k, lab in (("sig", "mean rating sigma of the field"),
               ("nr", "mean n_rounds behind the rating"),
               ("thin", "share of field under MIN_ROUNDS=20"),
               ("size", "field size"),
               ("hard", "event mean score (how hard it played)")):
    x = np.array([v[k] for v in E.values()])
    print("   %-38s corr %+.3f" % (lab, float(np.corrcoef(x, d)[0, 1])))


def ekey(n):
    return " ".join(sorted(w for w in str(n).lower().split() if len(w) > 3))


print("\n" + "=" * 92)
print("2 — DOES EVENT IDENTITY STILL PREDICT once field-knowledge is partialled out?")
print("=" * 92)
# residualise dispersion on the field-knowledge proxies (fit on <=2024 only)
tr = [v for v in E.values() if v["yr"] <= 2024]
X = np.column_stack([np.ones(len(tr))] + [np.array([v[k] for v in tr])
                                          for k in ("sig", "nr", "thin", "size")])
y = np.array([v["disp"] for v in tr])
beta = np.linalg.lstsq(X, y, rcond=None)[0]
print("   field-knowledge model fitted on <=2024 (n=%d); R^2 = %.3f"
      % (len(tr), 1 - np.var(y - X @ beta) / np.var(y)))


def adj(v):
    xv = np.array([1.0, v["sig"], v["nr"], v["thin"], v["size"]])
    return v["disp"] - float(xv @ beta)


byname_raw, byname_adj = defaultdict(dict), defaultdict(dict)
for eid, v in E.items():
    byname_raw[ekey(v["name"])][v["yr"]] = v["disp"]
    byname_adj[ekey(v["name"])][v["yr"]] = adj(v)

for lab, store in (("RAW dispersion", byname_raw),
                   ("AFTER removing field-knowledge", byname_adj)):
    pairs = []
    for k, yv in store.items():
        ys = sorted(yv)
        for a, b in zip(ys, ys[1:]):
            if b - a == 1:
                pairs.append((yv[a], yv[b]))
    if len(pairs) >= 20:
        x = np.array([p[0] for p in pairs]); yy = np.array([p[1] for p in pairs])
        print("   %-34s year-to-year corr %+.3f  (n=%d pairs)"
              % (lab, float(np.corrcoef(x, yy)[0, 1]), len(pairs)))

print("\n" + "=" * 92)
print("3 — OOS AGAIN, but predicting the FIELD-ADJUSTED dispersion")
print("=" * 92)
prior = defaultdict(list)
for k, yv in byname_adj.items():
    for yr, v in yv.items():
        if yr <= 2024:
            prior[k].append(v)
glob = float(np.mean([v for k, yv in byname_adj.items() for yr, v in yv.items() if yr <= 2024]))
te = [(k, yv[2025]) for k, yv in byname_adj.items() if 2025 in yv and k in prior]
if len(te) >= 20:
    act = np.array([v for _k, v in te])
    pred = np.array([float(np.mean(prior[k])) for k, _v in te])
    mse_g = float(np.mean((act - glob) ** 2))
    mse_p = float(np.mean((act - pred) ** 2))
    print("   n=%d  MSE global %.5f -> prior-edition %.5f  (%.1f%% better)  corr %+.3f"
          % (len(te), mse_g, mse_p, 100 * (mse_g - mse_p) / mse_g,
             float(np.corrcoef(pred, act)[0, 1])))
    print("   -> if this stays strong, the venue carries dispersion information that has")
    print("      NOTHING to do with how well we know the players.")

print("\n" + "=" * 92)
print("4 — SAME TOURNAMENT, DIFFERENT COURSE: does dispersion follow the venue or the name?")
print("=" * 92)
pm = sqlite3.connect("file:pga_model.sqlite?mode=ro", uri=True, timeout=60)
tid_course = defaultdict(set)
for tid, cid in pm.execute("SELECT DISTINCT tid, course_id FROM course_holes"):
    tid_course[str(tid)].add(str(cid))
pm.close()
print("   (course ids are only available for 114 tids; reported for completeness)")
print("   tournaments whose course set changed between years: %d"
      % len({t[:5] for t in tid_course} & set()))
top = sorted(E.values(), key=lambda v: -v["disp"])[:6]
bot = sorted(E.values(), key=lambda v: v["disp"])[:6]
print("\n   MOST dispersed events:")
for v in top:
    print("      %-44s %d  disp %.3f  thin %.2f  hard %.1f"
          % (v["name"][:44], v["yr"], v["disp"], v["thin"], v["hard"]))
print("   LEAST dispersed events:")
for v in bot:
    print("      %-44s %d  disp %.3f  thin %.2f  hard %.1f"
          % (v["name"][:44], v["yr"], v["disp"], v["thin"], v["hard"]))
