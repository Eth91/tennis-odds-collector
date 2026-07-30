"""Two questions, answered with the statistical power each deserves.

Q1 WIND x SKILL (pooled — high power). On a windier day, does a long/accurate driver beat their own
   rating by more? This pools every round, so unlike the per-course test it is not starved of data.
   Wind is the event's mean daily-max, deviated from the sample mean, so the coefficient is
   "extra strokes per unit skill per km/h above normal".

Q2 IS THE PER-COURSE DRIVING EFFECT REAL? The per-course SG_OTT spread beat sampling noise by only
   ~1.2 sigma across 4 tests, which is consistent with chance. The honest test is out-of-sample:
   estimate each course's driving-reward on its EARLY rounds and see whether it predicts the
   residual in its LATER rounds. Same design that showed personal course fit was ~nil.
"""
import datetime as dt
import math
import os
import shutil
import sqlite3
import statistics as st
from collections import defaultdict

import pga_context as C
import pga_ruler as RU
import sg_course_fit as CF

_SNAP = os.path.expanduser("~/pga_model_wf.sqlite")
shutil.copyfile(str(RU.DB), _SNAP)
RU.DB = _SNAP
CF.RU.DB = _SNAP
CATS = ["SG_OTT", "SG_APP", "SG_PUTT", "DRIVE_DIST", "DRIVE_ACC"]
CF.CATS = CATS

print("building analysis table (this refits ratings as-of each event)...")
data = CF.build()
print("rows: %d" % len(data))
if not data:
    raise SystemExit("no rows")

# ---------------------------------------------------------------- wind per event
con = sqlite3.connect(_SNAP)
evs = con.execute("SELECT event_id, event, MIN(date) FROM rounds GROUP BY event_id").fetchall()
con.close()
wind = {}
for eid, evn, d0 in evs:
    ck = CF._ckey(evn)
    if ck in wind:
        continue
    lat, lon = C._course_latlon(evn)
    if lat is None:
        continue
    try:
        start = dt.date.fromisoformat(str(d0)[:10])
    except (TypeError, ValueError):
        continue
    wm = C._archive_wind_range(lat, lon, start.isoformat(),
                              (start + dt.timedelta(days=4)).isoformat())
    vals = [v for v in (wm or {}).values() if v is not None]
    if vals:
        wind.setdefault(ck, []).append(st.mean(vals))
wind = {k: st.mean(v) for k, v in wind.items()}
print("courses with archived wind: %d" % len(wind))
if wind:
    mw = st.mean(wind.values())
    print("  mean event wind %.1f km/h (sd %.1f)" % (mw, st.pstdev(list(wind.values()))))

print()
print("=== Q1: WIND x SKILL (pooled). negative = skill helps MORE than its rating in wind ===")
print("    %-11s %14s %10s %9s" % ("skill", "interaction", "r", "n"))
for c in CATS:
    pts = []
    for ck, _yr, _p, res, s in data:
        w = wind.get(ck)
        if w is None or c not in s:
            continue
        pts.append(((w - mw) * s[c], res))
    b, r, n = CF.lin(pts)
    if b is None:
        print("    %-11s (too few)" % c)
        continue
    tag = ""
    if abs(r or 0) > 0.02:
        tag = "  <- notable"
    print("    %-11s %+13.5f %+10.3f %9d%s" % (c, b, r or 0, n, tag))
print("    interaction sign: NEGATIVE means high-skill players beat their rating MORE as wind rises")

print()
print("=== Q2: is the per-course DRIVING effect real? out-of-sample early -> late ===")
for c in ("SG_OTT", "DRIVE_DIST", "DRIVE_ACC"):
    by_c = defaultdict(list)
    for ck, yr, _p, res, s in data:
        if c in s:
            by_c[ck].append((yr, s[c], res))
    xs, ys = [], []
    for ck, v in by_c.items():
        if len(v) < 200:
            continue
        v.sort()
        h = len(v) // 2
        be, _r1, n1 = CF.lin([(x, r) for _y, x, r in v[:h]])
        bl, _r2, n2 = CF.lin([(x, r) for _y, x, r in v[h:]])
        if be is not None and bl is not None:
            xs.append(be)
            ys.append(bl)
    if len(xs) < 12:
        print("    %-11s only %d courses with enough rounds to split" % (c, len(xs)))
        continue
    b, r, n = CF.lin(list(zip(xs, ys)))
    verdict = ("PERSISTS — usable" if (b or 0) > 0.25 and (r or 0) > 0.25
               else "does NOT persist — early estimate does not predict later rounds")
    print("    %-11s %d courses | slope(late on early) %+.3f  r %+.3f -> %s"
          % (c, len(xs), b or 0, r or 0, verdict))
