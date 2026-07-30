#!/bin/bash
cd ~/tennis-odds-collector || exit 1
nice -n 8 timeout 1700 python3 -u - <<'PY'
"""Controlled: does DP World data in TRAINING help or hurt PGA-event prediction?

The naive comparison (0.5967 -> 0.5885) is confounded — the merge changed the TEST set too, adding
heterogeneous DP World events. The honest test holds the test set fixed at PGA events only and
varies only what the ratings were fit on. If the merge hurts, it ships as a regression.
"""
import os, random, shutil, sqlite3, statistics as st
from collections import defaultdict
import pga_ruler as RU

snap = os.path.expanduser("~/pga_model_ct.sqlite")
shutil.copyfile(str(RU.DB), snap); RU.DB = snap
con = sqlite3.connect(snap)
# ESPN event ids do not carry the tour, so identify DP World events by the players who only
# appear there: instead use the event NAME set from each league crawl. Simpler and exact:
# PGA events are those whose id appears in the pga scoreboard crawl -> tag by re-fetching ids.
import json, urllib.request
UA = {"User-Agent": "Mozilla/5.0"}
pga_ids = set()
for yr in (2023, 2024, 2025, 2026):
    try:
        j = json.load(urllib.request.urlopen(urllib.request.Request(
            "https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=%d" % yr,
            headers=UA), timeout=40))
        for ev in j.get("events") or []:
            pga_ids.add(str(ev.get("id")))
    except Exception as e:
        print("  (pga id fetch %d failed: %s)" % (yr, str(e)[:40]))
print("PGA event ids identified: %d" % len(pga_ids))

all_rows = RU.all_rows()
pga_rows = [r for r in all_rows if str(r[0]) in pga_ids]
print("rows: all %d | pga-only %d | dp-world %d"
      % (len(all_rows), len(pga_rows), len(all_rows) - len(pga_rows)))

evs = con.execute("SELECT event_id, MIN(date) d FROM rounds GROUP BY event_id "
                  "HAVING d >= '2026-01-01' ORDER BY d").fetchall()
con.close()
test_evs = [(e, d) for e, d in evs if str(e) in pga_ids]
print("TEST set held fixed: %d PGA events in 2026" % len(test_evs))

def run(train_rows, label):
    random.seed(11); hits = tot = 0; errs = []
    for eid, d0 in test_evs:
        R, _ = RU.fit(asof=d0, rows=train_rows)
        Rn = {RU.norm(k): v for k, v in R.items()}
        c = sqlite3.connect(snap)
        rr = c.execute("SELECT player, rnd, score FROM rounds WHERE event_id=? AND score>0",
                       (eid,)).fetchall()
        c.close()
        by = defaultdict(list)
        for pl, rnd, sc in rr:
            v = Rn.get(RU.norm(pl))
            if v: by[rnd].append((pl, v[0], sc))
        for rnd, lst in by.items():
            if len(lst) < 20: continue
            fm = st.mean(x[2] for x in lst)
            for _pl, rt, sc in lst: errs.append((sc - fm) - rt)
            for _ in range(60):
                (p1, r1, s1), (p2, r2, s2) = random.choice(lst), random.choice(lst)
                if p1 == p2 or s1 == s2 or abs(r1 - r2) < 0.15: continue
                tot += 1
                if (r1 < r2) == (s1 < s2): hits += 1
    acc = hits / tot if tot else 0
    rmse = (sum(e*e for e in errs)/len(errs))**0.5 if errs else 0
    print("  %-34s accuracy %.4f  RMSE %.4f  (%d pairs)" % (label, acc, rmse, tot))
    return acc

print()
print("=== SAME TEST SET (2026 PGA events only), training data varied ===")
a1 = run(pga_rows, "train: PGA only (before merge)")
a2 = run(all_rows, "train: PGA + DP World (merged)")
print()
d = a2 - a1
if d > 0.002:
    print("  -> MERGE HELPS (+%.4f). Keep it." % d)
elif d < -0.002:
    print("  -> MERGE HURTS (%.4f). It is a REGRESSION on PGA events — revert to pga-only" % d)
    print("     for the rating fit, or field-quality correction is not bridging the tours.")
else:
    print("  -> WASH (%+.4f). No predictive gain on PGA events; the merge's value is COVERAGE" % d)
    print("     for international fields, not accuracy. Keep it for that reason only.")
PY
