"""⛳ pga_context — the four contextual terms the model was blind to.

Each function answers one measured blindness from the 2026-07-29 audit:

  course_factor(event)   COURSE DIFFICULTY. Measured spread beyond par mix was 0.78x-1.29x
                         (sd 13%) — larger than any player edge. Prior editions of the SAME
                         event are the only honest pre-tournament read, and we have 4 seasons
                         of round scores. A scoring->birdie bridge (fitted on the events where
                         we hold BOTH hole data and scores) turns scores into a birdie factor,
                         so a course needs no hole-level history to be priced.
  field_strength(event)  FIELD DRIFT. Ratings are strokes-vs-field-mean, so a player who feeds
                         on opposite-field events is flattered. Returns each event's field
                         quality so the rating fit can subtract it (two-pass, below).
  course_fit(player,ev)  COURSE HISTORY. The player's own scoring at this event vs his form
                         at the time, shrunk hard (course history is famously overrated).
  wind_factor(kmh)       WEATHER. Fitted on real archived wind at the harvested events, so the
                         coefficient is measured rather than assumed.

Everything is shrunk toward "no effect" and every fit prints its own n, because a context
term with 3 observations behind it is a story, not a signal.
"""
import datetime as dt
import json
import math
import sqlite3
import statistics as st
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "pga_model.sqlite"
CACHE = HERE / "pga_context_cache.json"

K_COURSE = 2.0       # pseudo-editions of shrinkage on the course factor
K_FIT = 8.0          # pseudo-rounds of shrinkage on personal course fit (history is noisy)
WIND_REF = 15.0      # km/h reference: factors are relative to this


def _cache():
    try:
        return json.loads(CACHE.read_text())
    except Exception:                                              # noqa: BLE001
        return {}


def _save(c):
    try:
        CACHE.write_text(json.dumps(c))
    except OSError:
        pass


# ---------------------------------------------------------------- scoring baselines
def event_scoring():
    """{(event_name, season): (mean_score, n_rounds)} plus per-season baselines."""
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT event, date, score FROM rounds").fetchall()
    con.close()
    by = defaultdict(list)
    for ev, d, sc in rows:
        if not d:
            continue
        by[(ev.strip(), d[:4])].append(sc)
    ev_mean = {k: (st.mean(v), len(v)) for k, v in by.items() if len(v) >= 40}
    season = defaultdict(list)
    for (ev, yr), (m, n) in ev_mean.items():
        season[yr].append(m)
    base = {yr: st.mean(v) for yr, v in season.items() if v}
    return ev_mean, base


def _birdie_bridge():
    """Fit birdie_factor ~ a + b * (scoring_diff). Uses only events where we hold BOTH
    hole-level birdie data and round scores — that's what makes the bridge honest, and it
    lets any course with mere SCORES be priced for birdies."""
    c = _cache()
    if "bridge" in c:
        return c["bridge"]
    con = sqlite3.connect(DB)
    hole = con.execute(
        "SELECT tname, SUM(p3h), SUM(p3b), SUM(p4h), SUM(p4b), SUM(p5h), SUM(p5b) "
        "FROM birdie_rounds GROUP BY tname").fetchall()
    con.close()
    if not hole:
        return None
    # global per-par rates as the neutral expectation
    tot = defaultdict(lambda: [0, 0])
    for _t, a3, b3, a4, b4, a5, b5 in hole:
        for par, (h, b) in ((3, (a3, b3)), (4, (a4, b4)), (5, (a5, b5))):
            tot[par][0] += h
            tot[par][1] += b
    g = {p: (v[1] / v[0] if v[0] else 0.15) for p, v in tot.items()}
    ev_mean, base = event_scoring()
    xs, ys = [], []
    for tname, a3, b3, a4, b4, a5, b5 in hole:
        holes = a3 + a4 + a5
        if not holes:
            continue
        obs = (b3 + b4 + b5) / holes
        exp = (a3 * g[3] + a4 * g[4] + a5 * g[5]) / holes
        if exp <= 0:
            continue
        # match the event's scoring diff by fuzzy name
        cand = [(m, yr) for (ev, yr), (m, n) in ev_mean.items()
                if ev and tname and (ev.lower()[:14] in tname.lower()
                                     or tname.lower()[:14] in ev.lower())]
        if not cand:
            continue
        m, yr = cand[0]
        diff = m - base.get(yr, m)
        xs.append(diff)
        ys.append(obs / exp)
    if len(xs) < 6:
        return None
    mx, my = st.mean(xs), st.mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    b = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den) if den else 0.0
    a = my - b * mx
    r = None
    try:
        sx, sy = st.pstdev(xs), st.pstdev(ys)
        if sx and sy:
            r = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)) / (sx * sy)
        pass
    except Exception:                                              # noqa: BLE001
        pass
    out = {"a": a, "b": b, "n": len(xs), "r": r}
    c["bridge"] = out
    _save(c)
    return out


def course_factor(event_name, verbose=False):
    """Birdie-rate multiplier for a course, from PRIOR editions' scoring. 1.0 = neutral.
    Shrunk toward 1.0 by K_COURSE pseudo-editions so one weird year cannot dominate."""
    br = _birdie_bridge()
    ev_mean, base = event_scoring()
    key = (event_name or "").strip().lower()
    toks = [w for w in key.replace("pga", "").split() if len(w) > 3 and not w.isdigit()]
    diffs = []
    for (ev, yr), (m, n) in ev_mean.items():
        el = ev.lower()
        if toks and sum(1 for w in toks if w in el) >= max(1, len(toks) // 2):
            diffs.append(m - base.get(yr, m))
    if not diffs or not br:
        if verbose:
            print(f"  course_factor({event_name}): no prior editions -> 1.00")
        return 1.0, 0
    d = st.mean(diffs)
    raw = br["a"] + br["b"] * d
    n = len(diffs)
    fac = 1.0 + (raw - 1.0) * n / (n + K_COURSE)
    fac = max(0.75, min(1.30, fac))
    if verbose:
        print(f"  course_factor({event_name}): {n} prior edition(s), scoring {d:+.2f} "
              f"vs season -> factor {fac:.3f}  (bridge n={br['n']}, r={br.get('r')})")
    return fac, n


# ---------------------------------------------------------------- field strength
def field_strength(ratings=None):
    """{(event, season): mean rating of its field} — the correction for field drift.
    Ratings are strokes-vs-field-mean, so without this a player who only tees it up in
    weak fields reads as better than he is."""
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT event, date, player FROM rounds").fetchall()
    con.close()
    if ratings is None:
        import pga_ruler as RU
        R, _ = RU.fit()
        ratings = {k: v[0] for k, v in R.items()}
    by = defaultdict(list)
    for ev, d, pl in rows:
        r = ratings.get(pl)
        if r is not None and d:
            by[(ev.strip(), d[:4])].append(r)
    return {k: st.mean(v) for k, v in by.items() if len(v) >= 40}


# ---------------------------------------------------------------- personal course fit
def course_fit(player, event_name):
    """Strokes/round the player has historically beaten HIS OWN average by at this event.
    Shrunk by K_FIT — course history is the most over-claimed edge in golf."""
    con = sqlite3.connect(DB)
    key = (event_name or "").strip().lower()
    toks = [w for w in key.replace("pga", "").split() if len(w) > 3 and not w.isdigit()]
    if not toks:
        con.close()
        return 0.0, 0
    like = "%" + toks[0] + "%"
    here_ = [r[0] for r in con.execute(
        "SELECT score FROM rounds WHERE player=? AND LOWER(event) LIKE ?", (player, like))]
    allr = [r[0] for r in con.execute("SELECT score FROM rounds WHERE player=?", (player,))]
    con.close()
    if len(here_) < 2 or len(allr) < 20:
        return 0.0, len(here_)
    d = st.mean(here_) - st.mean(allr)
    n = len(here_)
    return d * n / (n + K_FIT), n


# ---------------------------------------------------------------- weather
def _archive_wind(lat, lon, day):
    """Mean daily wind (km/h) from open-meteo's free ARCHIVE api."""
    u = ("https://archive-api.open-meteo.com/v1/archive?latitude=%s&longitude=%s"
         "&start_date=%s&end_date=%s&daily=wind_speed_10m_max&timezone=UTC"
         % (lat, lon, day, day))
    try:
        d = json.load(urllib.request.urlopen(
            urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=25))
        v = ((d.get("daily") or {}).get("wind_speed_10m_max") or [None])[0]
        return v
    except Exception:                                              # noqa: BLE001
        return None


def _course_latlon(tid, cache_key="courses"):
    """(lat, lon) for a tournament's host course: courseStats name -> open-meteo geocode."""
    import pga_birdies as B
    c = _cache()
    store = c.get(cache_key) or {}
    if str(tid) in store:
        return tuple(store[str(tid)])
    name = None
    try:
        d = B.gql('query C(' + chr(36) + 't: ID!) {courseStats(tournamentId: ' + chr(36)
                  + 't) {courses {courseName hostCourse}}}', {"t": tid})
        cs = ((d.get("data") or {}).get("courseStats") or {}).get("courses") or []
        host = next((x for x in cs if x.get("hostCourse")), cs[0] if cs else None)
        name = (host or {}).get("courseName")
    except Exception:                                              # noqa: BLE001
        pass
    if not name:
        return None, None
    try:
        u = ("https://geocoding-api.open-meteo.com/v1/search?count=1&name="
             + urllib.request.quote(name))
        g = json.load(urllib.request.urlopen(
            urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=25))
        r0 = (g.get("results") or [{}])[0]
        lat, lon = r0.get("latitude"), r0.get("longitude")
    except Exception:                                              # noqa: BLE001
        return None, None
    if lat is not None:
        store[str(tid)] = [lat, lon]
        c[cache_key] = store
        _save(c)
    return lat, lon


def fit_wind(verbose=True, refit=False):
    """Fit birdie_factor ~ 1 + w*(wind - WIND_REF) on harvested events using REAL archived
    wind at EACH event's own course. A non-negative coefficient is REJECTED (wind does not
    make golf easier) and replaced by a small negative default flagged assumed=True."""
    c = _cache()
    if "wind" in c and not refit:
        return c["wind"]
    import pga_birdies as B
    con = sqlite3.connect(DB)
    evs = con.execute("SELECT tid, tname FROM birdie_rounds GROUP BY tid").fetchall()
    rows = con.execute(
        "SELECT tid, SUM(p3h), SUM(p3b), SUM(p4h), SUM(p4b), SUM(p5h), SUM(p5b) "
        "FROM birdie_rounds GROUP BY tid").fetchall()
    con.close()
    agg = {r[0]: r[1:] for r in rows}
    _, fr = B.rates()
    xs, ys, seen = [], [], []
    for tid, tname in evs:
        a3, b3, a4, b4, a5, b5 = agg.get(tid, (0,) * 6)
        holes = a3 + a4 + a5
        if not holes:
            continue
        obs = (b3 + b4 + b5) / holes
        exp = (a3 * fr[3] + a4 * fr[4] + a5 * fr[5]) / holes
        if exp <= 0:
            continue
        lat, lon = _course_latlon(tid)
        if lat is None:
            continue
        con = sqlite3.connect(DB)
        d0 = con.execute("SELECT MIN(date), MAX(date) FROM rounds WHERE LOWER(event) LIKE ?",
                         ("%" + (tname or "")[:14].lower() + "%",)).fetchone()
        con.close()
        if not d0 or not d0[0]:
            continue
        w = _archive_wind(lat, lon, d0[0])
        if w is None:
            continue
        xs.append(w)
        ys.append(obs / exp)
        seen.append((tname[:26], round(w, 1), round(obs / exp, 3)))
    out = None
    if len(xs) >= 6:
        mx, my = st.mean(xs), st.mean(ys)
        den = sum((x - mx) ** 2 for x in xs)
        b = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den) if den else 0.0
        sx, sy = (st.pstdev(xs) or 1), (st.pstdev(ys) or 1)
        r = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)) / (sx * sy)
        if verbose:
            for t, w_, f_ in sorted(seen, key=lambda z: z[1]):
                print(f"     {t:<28} wind {w_:>5} km/h  factor {f_:.3f}")
            print(f"  fit: n={len(xs)} coefficient {b:+.5f}/km/h  r={r:+.2f}")
        if b < 0:
            out = {"w": b, "n": len(xs), "assumed": False, "r": r}
        else:
            if verbose:
                print("  REJECTED: non-negative coefficient (wind cannot make golf easier)"
                      " -> pinning a small negative default, flagged assumed")
            out = {"w": -0.003, "n": len(xs), "assumed": True, "r": r}
    else:
        if verbose:
            print(f"  fit_wind: only {len(xs)} usable events -> conservative default")
        out = {"w": -0.003, "n": len(xs), "assumed": True}
    c["wind"] = out
    _save(c)
    return out


def wind_factor(kmh):
    """Birdie multiplier for a given wind speed, floored/capped so a forecast spike can
    never dominate the price."""
    f = fit_wind(verbose=False)
    if kmh is None:
        return 1.0
    return max(0.80, min(1.15, 1.0 + f["w"] * (kmh - WIND_REF)))


if __name__ == "__main__":
    br = _birdie_bridge()
    print("scoring->birdie bridge:", br)
    for ev in ("Rocket Classic", "Masters Tournament", "Valspar Championship",
               "The American Express"):
        course_factor(ev, verbose=True)
    print()
    print("wind fit:", fit_wind())
    for w in (5, 15, 25, 40):
        print(f"   wind {w:>2} km/h -> factor {wind_factor(w):.3f}")
    print()
    for p in ("Rickie Fowler", "Hideki Matsuyama"):
        d, n = course_fit(p, "Rocket Classic")
        print(f"course_fit({p}, Rocket Classic): {d:+.2f} strokes/round over {n} rounds")
