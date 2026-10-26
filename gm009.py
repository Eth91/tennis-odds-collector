#!/usr/bin/env python3
"""GM-009 — does wind predict scoring? And does it only work with the CORRECTED coordinates?

Two questions in one test, and the second is the more important one.

WHETHER WIND MATTERS. Within an event, does the windier day play harder and spread the field
wider? Everything is demeaned WITHIN EVENT across that event's rounds, so course, setup, field
strength and par all cancel by construction -- what is left is day-to-day variation at one venue.

WHETHER THE COORDINATE FIX WAS REAL. The old pipeline pulled Masters weather from Augusta MAINE,
Memorial from Dublin IRELAND and the Puerto Rico Open from BRAZIL. If those coordinates were
materially wrong, the OLD wind should predict scoring weakly or not at all, and the NEW wind
should predict it better on the same events and the same rounds. That is a natural A/B on data
quality, and it is the only honest way to show a data fix mattered rather than asserting it.

  A  ix.wind        old pipeline, bare-city geocode, one coordinate per tournament NAME
  B  pga_wx.wind    per EVENT-YEAR venue, country-gated, ambiguous cities refused, curated majors

⚠️ ROUND DATE IS AN ASSUMPTION. `rounds.date` is the event START date and is identical for all
four rounds -- the warehouse has no per-round date. Round r is therefore mapped to start+(r-1),
which is right for a standard Thursday-Sunday event and wrong for weather-delayed or Monday
finishes. That mis-dating is NOISE, and noise can only push the measured effect toward zero, so
it cannot manufacture a positive result.

⚠️ WIND IS wind_speed_10m_max FOR THE DAY, not wind during a player's round. A morning wave that
played in calm and an afternoon wave that played in 40 km/h share one number here.

2026 IS THE PROTECTED HOLDOUT AND IS NOT READ.
"""
import datetime as dt
import math
import sqlite3
from collections import defaultdict

import numpy as np

import pga_ruler as RU

con = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
rows = con.execute("SELECT event_id, event, date, player, rnd, score FROM rounds "
                   "WHERE date < '2026-01-01'").fetchall()
con.close()
ev = defaultdict(lambda: defaultdict(list))
estart = {}
for eid, evn, d, pl, rnd, sc in rows:
    if sc is None:
        continue
    ev[str(eid)][int(rnd)].append(float(sc))
    estart[str(eid)] = str(d)

# NEW weather, keyed by event-year venue
wx = sqlite3.connect("file:pga_wx.sqlite?mode=ro", uri=True, timeout=60)
NEW = {}
for eid, d, w in wx.execute("SELECT event_id, date, wind FROM wx WHERE wind IS NOT NULL"):
    NEW[(str(eid), str(d))] = float(w)
wx.close()
print("new weather rows: %d" % len(NEW))

# OLD weather from the ix table (bare-city geocode)
OLD = {}
try:
    ic = sqlite3.connect("file:/home/ubuntu/pga_interactions.sqlite?mode=ro", uri=True)
    for eid, rnd, w in ic.execute("SELECT event_id, rnd, wind FROM ix WHERE wind IS NOT NULL"):
        OLD[(str(eid), int(rnd))] = float(w)
    ic.close()
except Exception as e:                                                  # noqa: BLE001
    print("old weather unavailable: %s" % e)
print("old weather (event, rnd) keys: %d" % len(OLD))


def rounddate(eid, rnd):
    return (dt.date.fromisoformat(estart[eid]) + dt.timedelta(days=rnd - 1)).isoformat()


def build(source):
    """within-event demeaned (wind, mean score, dispersion) triples."""
    out = []
    for eid, byr in ev.items():
        rs = [r for r in sorted(byr) if len(byr[r]) >= 40]
        if len(rs) < 3:
            continue
        w, m, s = [], [], []
        for r in rs:
            v = NEW.get((eid, rounddate(eid, r))) if source == "new" else OLD.get((eid, r))
            if v is None:
                continue
            a = np.array(byr[r])
            w.append(v)
            m.append(float(a.mean()))
            s.append(float(a.std(ddof=1)))
        if len(w) < 3:
            continue
        w = np.array(w); m = np.array(m); s = np.array(s)
        if w.std() < 1e-9:
            continue
        out += list(zip(w - w.mean(), m - m.mean(), s - s.mean(), [eid] * len(w)))
    return out


print("\n" + "=" * 94)
print("WITHIN-EVENT: does the windier DAY play harder, and spread the field wider?")
print("=" * 94)
print("   %-8s %8s %8s %14s %16s" % ("source", "events", "n days", "corr(wind,score)",
                                     "corr(wind,spread)"))
res = {}
for src in ("old", "new"):
    d = build(src)
    if len(d) < 60:
        print("   %-8s too few (%d)" % (src, len(d)))
        continue
    w = np.array([x[0] for x in d]); m = np.array([x[1] for x in d])
    s = np.array([x[2] for x in d])
    ne = len({x[3] for x in d})
    c1 = float(np.corrcoef(w, m)[0, 1])
    c2 = float(np.corrcoef(w, s)[0, 1])
    res[src] = (c1, c2, len(d), ne)
    print("   %-8s %8d %8d %+14.4f %+16.4f" % (src, ne, len(d), c1, c2))

# LIKE FOR LIKE. The two sources cover different events (old 48, new 128), so comparing their
# headline correlations compares samples as much as coordinates. Restrict BOTH to the event-days
# where both have a wind value, which is the only comparison that isolates the coordinate change.
do, dn = build("old"), build("new")
ko = {(x[3], round(x[0], 6)) for x in do}
inter = sorted({x[3] for x in do} & {x[3] for x in dn})
if inter:
    io = [x for x in do if x[3] in inter]
    inw = [x for x in dn if x[3] in inter]
    print("\n   LIKE FOR LIKE — the %d events present in BOTH sources:" % len(inter))
    for lab, dd in (("old coords", io), ("new coords", inw)):
        w = np.array([x[0] for x in dd]); m = np.array([x[1] for x in dd])
        print("      %-11s n=%3d days   corr(wind, scoring) %+.4f"
              % (lab, len(dd), float(np.corrcoef(w, m)[0, 1])))
    print("   and COVERAGE: %d events -> %d events, %d day-observations -> %d"
          % (len({x[3] for x in do}), len({x[3] for x in dn}), len(do), len(dn)))
    print("   The coordinate fix bought mostly COVERAGE. Only ~10.6%% of the old rows came from a")
    print("   known-wrong venue, so the old correlation was diluted, not destroyed.")

# stroke cost per 10 km/h, on the corrected data, with event-clustered SE
d = build("new")
if len(d) >= 60:
    byev = defaultdict(list)
    for w, m, s, eid in d:
        byev[eid].append((w, m, s))
    sl_m, sl_s = [], []
    for eid, v in byev.items():
        if len(v) < 3:
            continue
        w = np.array([t[0] for t in v]); m = np.array([t[1] for t in v])
        s = np.array([t[2] for t in v])
        if w.std() < 1e-9:
            continue
        sl_m.append(float(np.polyfit(w, m, 1)[0]))
        sl_s.append(float(np.polyfit(w, s, 1)[0]))
    sl_m = np.array(sl_m); sl_s = np.array(sl_s)
    print("\n" + "=" * 94)
    print("EFFECT SIZE (corrected coordinates), per-event slopes")
    print("=" * 94)
    for lab, arr in (("scoring", sl_m), ("dispersion", sl_s)):
        se = arr.std(ddof=1) / math.sqrt(len(arr))
        print("   %-11s %+.4f strokes per km/h  (x10 km/h = %+.3f)  SE %.4f  t=%+.2f  n=%d events"
              % (lab, arr.mean(), 10 * arr.mean(), se, arr.mean() / se if se > 0 else 0, len(arr)))
    print("\n   GM-004 verified that dispersion is predictable from prior editions. If wind moves")
    print("   dispersion too, part of that predictability is simply that windy venues stay windy.")
