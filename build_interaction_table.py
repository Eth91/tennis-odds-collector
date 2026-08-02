"""Build ONE cached table of round-level residuals x skills x weather, then scan interactions.

Speed: every test so far rebuilt the residual table by refitting ratings as-of all 293 events
(~10 min). That is now done ONCE and cached to sqlite, so every interaction test afterwards runs in
seconds.

Weather is pulled PER ROUND-DAY, not per event, so a Thursday that rained and a Sunday that did not
are different observations. Sources are open-meteo's archive (free, no key):
    wind_speed_10m_max, precipitation_sum, temperature_2m_max/min, relative_humidity_2m_mean
Precipitation on the PRIOR days is the softness proxy — greens hold water from yesterday's rain,
which is the mechanism, not today's total.

DATA QUALITY: the stat labels are verified against the API's own statTitle before anything is
computed, because two silent errors already slipped through (driving accuracy harvested zero rows
because the parser only read "Avg", and 02420 was labeled GIR when it is Distance from Edge of
Fairway). A wrong label is worse than missing data — it gets analysed as if it were right.
"""
import datetime as dt
import json
import os
import shutil
import sqlite3
import statistics as st
import urllib.request
from collections import defaultdict

import pga_birdies as B
import pga_context as C
import pga_ruler as RU

SNAP = os.path.expanduser("~/pga_model_ix.sqlite")
OUT = os.path.expanduser("~/pga_interactions.sqlite")
shutil.copyfile(str(RU.DB), SNAP)
RU.DB = SNAP
D = chr(36)
UA = {"User-Agent": "Mozilla/5.0"}

# label -> (statId, expected substring in the API's own title)
STAT_CHECK = {
    "SG_OTT": ("02567", "off-the-tee"), "SG_APP": ("02568", "approach"),
    "SG_ARG": ("02569", "around-the-green"), "SG_PUTT": ("02564", "putting"),
    "SG_T2G": ("02674", "tee-to-green"), "SG_TOT": ("02675", "total"),
    "DRIVE_DIST": ("101", "distance"), "DRIVE_ACC": ("102", "accuracy"),
    "GIR": ("103", "greens in regulation"), "SCRAMBLE": ("130", "scrambling"),
}


def verify_labels():
    """Assert every label matches the API's own title. Catches the class of bug already seen."""
    q = ('query SD(%st: TourCode!, %ss: String!, %sy: Int!) '
         '{statDetails(tourCode: %st, statId: %ss, year: %sy) {statTitle}}' % (D, D, D, D, D, D))
    bad = []
    for label, (sid, want) in STAT_CHECK.items():
        try:
            d = B.gql(q, {"t": "R", "s": sid, "y": 2025})
            title = ((d.get("data") or {}).get("statDetails") or {}).get("statTitle") or ""
        except Exception as e:                                      # noqa: BLE001
            title = "ERR " + str(e)[:30]
        ok = want in title.lower()
        print("   %-11s id=%-6s title=%-38s %s"
              % (label, sid, title[:38], "OK" if ok else "*** MISLABELED ***"))
        if not ok:
            bad.append((label, sid, title))
    return bad


def weather_for(course_key, days):
    """{date: {wind,precip,tmax,tmin,rh}} for a course over a date range."""
    lat, lon = C._course_latlon(course_key)
    if lat is None or not days:
        return {}
    d0 = (min(days) - dt.timedelta(days=3)).isoformat()
    d1 = max(days).isoformat()
    u = ("https://archive-api.open-meteo.com/v1/archive?latitude=%s&longitude=%s"
         "&start_date=%s&end_date=%s&daily=wind_speed_10m_max,precipitation_sum,"
         "temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean&timezone=UTC"
         % (lat, lon, d0, d1))
    try:
        j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=35))
    except Exception:                                               # noqa: BLE001
        return {}
    dd = j.get("daily") or {}
    ts = dd.get("time") or []
    out = {}
    for i, t in enumerate(ts):
        def g(k):
            v = (dd.get(k) or [])
            return v[i] if i < len(v) else None
        out[t] = {"wind": g("wind_speed_10m_max"), "precip": g("precipitation_sum"),
                  "tmax": g("temperature_2m_max"), "tmin": g("temperature_2m_min"),
                  "rh": g("relative_humidity_2m_mean")}
    return out


def ckey(name):
    return " ".join(sorted(w for w in str(name or "").lower().split() if len(w) > 3))


def main():
    print("=== DATA QUALITY: verify every stat label against the API's own title ===")
    bad = verify_labels()
    if bad:
        print("   REFUSING to build with mislabeled stats:", [b[0] for b in bad])
        return
    print("   all labels verified")

    con = sqlite3.connect(SNAP)
    sg = defaultdict(dict)
    for yr, stat, player, avg in con.execute(
            "SELECT year, stat, player, avg FROM sg_stats WHERE avg IS NOT NULL"):
        sg[(RU.norm(player), yr)][stat] = avg
    evs = con.execute("SELECT event_id, event, MIN(date) FROM rounds GROUP BY event_id "
                      "ORDER BY MIN(date)").fetchall()
    con.close()
    CATS = sorted(STAT_CHECK)

    def sg_asof(year, hl=1.5):
        acc = {}
        for (p, y), d in sg.items():
            if y >= year:
                continue
            w = 0.5 ** ((year - 1 - y) / hl)
            a = acc.setdefault(p, {})
            for c, v in d.items():
                s = a.setdefault(c, [0.0, 0.0])
                s[0] += v * w
                s[1] += w
        return {p: {c: v[0] / v[1] for c, v in d.items() if v[1] > 0} for p, d in acc.items()}

    o = sqlite3.connect(OUT)
    o.execute("DROP TABLE IF EXISTS ix")
    o.execute("""CREATE TABLE ix(course TEXT, event_id TEXT, date TEXT, year INT, rnd INT,
        player TEXT, resid REAL, wind REAL, precip0 REAL, precip1 REAL, precip3 REAL,
        tmax REAL, rh REAL, %s)""" % ", ".join("%s REAL" % c for c in CATS))
    rows_all = RU.all_rows()
    wcache, sgcache = {}, {}
    n = 0
    for eid, evn, d0 in evs:
        try:
            yr = int(str(d0)[:4])
            start = dt.date.fromisoformat(str(d0)[:10])
        except (TypeError, ValueError):
            continue
        if yr not in sgcache:
            sgcache[yr] = sg_asof(yr)
        SG = sgcache[yr]
        if not SG:
            continue
        ck = ckey(evn)
        if ck not in wcache:
            wcache[ck] = weather_for(evn, [start + dt.timedelta(days=i) for i in range(5)])
        W = wcache[ck]
        R, _ = RU.fit(asof=d0, rows=rows_all)
        Rn = {RU.norm(k): v for k, v in R.items()}
        con = sqlite3.connect(SNAP)
        rr = con.execute("SELECT player, rnd, score FROM rounds WHERE event_id=? AND score>0",
                         (eid,)).fetchall()
        con.close()
        by = defaultdict(list)
        for pl, rnd, sc in rr:
            by[rnd].append((RU.norm(pl), sc))
        batch = []
        for rnd, lst in by.items():
            if len(lst) < 40 or not rnd:
                continue
            fm = st.mean(s for _p, s in lst)
            day = (start + dt.timedelta(days=int(rnd) - 1)).isoformat()
            w = W.get(day) or {}
            p0 = (W.get(day) or {}).get("precip")
            p1 = (W.get((start + dt.timedelta(days=int(rnd) - 2)).isoformat()) or {}).get("precip")
            p3 = 0.0
            got3 = False
            for k in range(2, 5):
                v = (W.get((start + dt.timedelta(days=int(rnd) - 1 - k)).isoformat())
                     or {}).get("precip")
                if v is not None:
                    p3 += v
                    got3 = True
            for p, sc in lst:
                v = Rn.get(p)
                s = SG.get(p)
                if not v or not s:
                    continue
                batch.append([ck, str(eid), day, yr, int(rnd), p, (sc - fm) - v[0],
                              w.get("wind"), p0, p1, (p3 if got3 else None),
                              w.get("tmax"), w.get("rh")]
                             + [s.get(c) for c in CATS])
        if batch:
            o.executemany("INSERT INTO ix VALUES (%s)" % ",".join("?" * (13 + len(CATS))), batch)
            o.commit()
            n += len(batch)
    tot = o.execute("SELECT COUNT(*), COUNT(DISTINCT course), COUNT(DISTINCT event_id) FROM ix"
                    ).fetchone()
    wx = o.execute("SELECT COUNT(*) FROM ix WHERE wind IS NOT NULL").fetchone()[0]
    px = o.execute("SELECT COUNT(*) FROM ix WHERE precip1 IS NOT NULL").fetchone()[0]
    o.close()
    print()
    print("cached -> %s" % OUT)
    print("  %d rows over %d courses / %d events | wind on %d (%.0f%%) | prior-day rain on %d (%.0f%%)"
          % (tot[0], tot[1], tot[2], wx, 100 * wx / max(tot[0], 1), px, 100 * px / max(tot[0], 1)))


if __name__ == "__main__":
    main()
