"""Two more assumed numbers.

WIND_REF = 15 km/h sets where the wind factor equals 1.0. fit_wind fits its slope on
WITHIN-EVENT demeaned data, so the slope is unbiased — but the factor is then applied as
1 + w*(kmh - WIND_REF). If typical tournament wind is not 15, the term is systematically off
at average conditions, and that offset gets silently absorbed by the course factor or the
market anchor. WIND_REF should be the MEAN wind of the fitting sample so the term is mean-zero.

n_sims = 8000 is a Monte Carlo precision choice, not a model parameter, but it sets a noise
floor under every probability we quote and therefore under every edge. Worth knowing whether
that floor is small relative to the 5-point edge threshold.
"""
import datetime as dt
import os
import sqlite3
import statistics as st

import pga_context as C
import pga_ruler as RU

RU.DB = os.path.expanduser("~/pga_model_snap.sqlite")

print("[A] WIND_REF — is 15 km/h the typical tournament wind?")
cache = C._cache()
ll = cache.get("latlon") or {}
con = sqlite3.connect(RU.DB)
tn = [r[0] for r in con.execute("SELECT DISTINCT tname FROM birdie_rounds").fetchall()]
con.close()
winds = []
for t in tn:
    v = ll.get(str(t))
    if not v:
        continue
    lat, lon = v[0], v[1]
    eid, d0 = C._espn_event_id(t)
    if not d0:
        continue
    try:
        start = dt.date.fromisoformat(str(d0)[:10])
    except ValueError:
        continue
    wm = C._archive_wind_range(lat, lon, start.isoformat(),
                               (start + dt.timedelta(days=4)).isoformat())
    if wm:
        winds += [w for w in wm.values() if w is not None]
if winds:
    print("    %d event-days of archived wind" % len(winds))
    print("    mean %.2f km/h | median %.2f | current WIND_REF = %.1f"
          % (st.mean(winds), st.median(winds), C.WIND_REF))
    off = (st.mean(winds) - C.WIND_REF)
    w = (C.fit_wind(verbose=False) or {}).get("w") or 0
    print("    => at MEAN wind the factor is %.4f, not 1.0 — a %+.2f%% standing bias in every"
          % (1 + w * off, 100 * w * off))
    print("       birdie price, absorbed invisibly by the course factor or the market anchor.")
    print("    RECOMMEND WIND_REF = %.1f" % st.mean(winds))
else:
    print("    no cached coordinates -> cannot measure")

print()
print("[B] n_sims = 8000 — how much Monte Carlo noise is under each quoted probability?")
import pga_field as PF
R, _ = RU.fit()
field = [(c.get("athlete") or {}).get("displayName") for c in PF.competitors()]
field = [f for f in field if f]
runs = {}
for seed in (1, 2, 3, 4, 5):
    sim = RU.simulate(R, field, n_sims=8000, seed=seed)
    for p, v in sim.items():
        runs.setdefault(p, []).append(v)
if runs:
    for key in ("win", "top5", "top10", "top20", "cut"):
        sds = [st.pstdev([r[key] for r in v]) for v in runs.values() if len(v) == 5]
        mx = max(sds)
        print("    %-6s across 5 seeds: mean seed-to-seed sd %.4f, worst %.4f (%.2f pts)"
              % (key, st.mean(sds), mx, 100 * mx))
    print("    edge threshold is 5.00 pts, so worst-case MC noise is ~%.0f%% of the threshold"
          % (100 * max(max(st.pstdev([r[k] for r in v]) for v in runs.values() if len(v) == 5)
                       for k in ("top5", "top10", "top20")) / 0.05))
