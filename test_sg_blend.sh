#!/bin/bash
cd ~/tennis-odds-collector || exit 1
nice -n 8 timeout 1700 python3 -u - <<'PY'
"""Direct test: does SG improve OUR ruler's predictions? Same test set, one variable.

The partial correlations said SG adds ~nothing beyond SG_TOT, but our rating is NOT SG_TOT — it is
recency-weighted, field-quality-corrected and now multi-tour. So test it head on.

LEAK CONTROL: for a 2026 event, only SG from seasons <= 2025 is used. Season-level SG for the
current year is computed FROM the rounds we are predicting, so including it would be circular.

Two forms tried:
  BLEND        rating + L*( -SG_TOT_prior - rating )      pull toward the SG-implied rating
  COMPOSITION  rating + B*SG_PUTT_prior                   penalise scores earned by putting,
                                                          the least persistent category
"""
import os, random, shutil, sqlite3, statistics as st
from collections import defaultdict
import pga_ruler as RU, json, urllib.request

snap = os.path.expanduser("~/pga_model_sgb.sqlite")
shutil.copyfile(str(RU.DB), snap); RU.DB = snap
UA = {"User-Agent": "Mozilla/5.0"}
pga_ids = set()
for yr in (2023, 2024, 2025, 2026):
    try:
        j = json.load(urllib.request.urlopen(urllib.request.Request(
            "https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=%d" % yr,
            headers=UA), timeout=40))
        for ev in j.get("events") or []: pga_ids.add(str(ev.get("id")))
    except Exception: pass

con = sqlite3.connect(snap)
sgrows = con.execute("SELECT year, stat, player, avg FROM sg_stats WHERE avg IS NOT NULL").fetchall()
evs = con.execute("SELECT event_id, MIN(date) d FROM rounds GROUP BY event_id "
                  "HAVING d >= '2026-01-01' ORDER BY d").fetchall()
con.close()
test_evs = [(e, d) for e, d in evs if str(e) in pga_ids]
print("test set: %d 2026 PGA events" % len(test_evs))

def sg_asof(max_year, half_life_y=1.5):
    acc = {}
    cur = max_year
    for yr, stat, player, avg in sgrows:
        if yr > max_year:            # LEAK GUARD: never use the season being predicted
            continue
        w = 0.5 ** ((cur - yr) / half_life_y)
        d = acc.setdefault(RU.norm(player), {}).setdefault(stat, [0.0, 0.0])
        d[0] += avg * w; d[1] += w
    return {p: {s: v[0]/v[1] for s, v in d.items() if v[1] > 0} for p, d in acc.items()}

SG = sg_asof(2025)
print("SG players available as-of 2025: %d" % len(SG))
rows_all = RU.all_rows()
FITS = {}

def run(mode, param):
    random.seed(11); hits = tot = 0; cov = 0; seen = 0
    for eid, d0 in test_evs:
        if d0 not in FITS:
            R, _ = RU.fit(asof=d0, rows=rows_all)
            FITS[d0] = {RU.norm(k): v for k, v in R.items()}
        Rn = FITS[d0]
        c = sqlite3.connect(snap)
        rr = c.execute("SELECT player, rnd, score FROM rounds WHERE event_id=? AND score>0",
                       (eid,)).fetchall()
        c.close()
        by = defaultdict(list)
        for pl, rnd, sc in rr:
            p = RU.norm(pl); v = Rn.get(p)
            if not v: continue
            rt = v[0]; s = SG.get(p)
            seen += 1
            if s:
                cov += 1
                if mode == "blend" and s.get("SG_TOT") is not None:
                    rt = rt + param * ((-s["SG_TOT"]) - rt)
                elif mode == "comp" and s.get("SG_PUTT") is not None:
                    rt = rt + param * s["SG_PUTT"]
            by[rnd].append((pl, rt, sc))
        for rnd, lst in by.items():
            if len(lst) < 20: continue
            for _ in range(60):
                (p1, r1, s1), (p2, r2, s2) = random.choice(lst), random.choice(lst)
                if p1 == p2 or s1 == s2 or abs(r1 - r2) < 0.15: continue
                tot += 1
                if (r1 < r2) == (s1 < s2): hits += 1
    return (hits/tot if tot else 0), tot, (100*cov/max(seen,1))

base, n, covpct = run("blend", 0.0)
print("SG coverage of rated player-rounds in the test set: %.0f%%" % covpct)
print()
print("  BLEND   rating + L*(-SG_TOT_prior - rating)")
print("    %-8s %10s %8s" % ("lambda", "accuracy", "delta"))
for L in (0.0, 0.10, 0.20, 0.35, 0.50):
    a, t, _ = run("blend", L)
    print("    %-8.2f %10.4f %+8.4f%s" % (L, a, a-base, "   <- current" if L == 0 else ""))
print()
print("  COMPOSITION  rating + B*SG_PUTT_prior  (penalise putting-earned scores)")
print("    %-8s %10s %8s" % ("beta", "accuracy", "delta"))
for Bq in (0.0, 0.10, 0.25, 0.50):
    a, t, _ = run("comp", Bq)
    print("    %-8.2f %10.4f %+8.4f%s" % (Bq, a, a-base, "   <- current" if Bq == 0 else ""))
PY
