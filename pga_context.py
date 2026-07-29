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


def direct_course_birdie_factor(event_name):
    """Observed/expected BIRDIE rate at this course from prior editions we hold hole-level
    data for. This is the measurement the bridge was standing in for: the bridge infers
    birdies from scoring (r=-0.68 — good, but lossy), while this counts the actual holes.
    Returns (factor, n_editions, n_rounds); factor is None with no direct history."""
    key = (event_name or "").strip().lower()
    toks = [w for w in key.replace("pga", "").split() if len(w) > 3 and not w.isdigit()]
    if not toks:
        return None, 0, 0
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT tid, tname, COUNT(*), SUM(p3h), SUM(p3b), SUM(p4h), SUM(p4b), "
        "SUM(p5h), SUM(p5b) FROM birdie_rounds GROUP BY tid").fetchall()
    tot = con.execute("SELECT SUM(p3h), SUM(p3b), SUM(p4h), SUM(p4b), SUM(p5h), SUM(p5b) "
                      "FROM birdie_rounds").fetchone()
    con.close()
    if not tot or not tot[0]:
        return None, 0, 0
    g = {3: tot[1] / tot[0] if tot[0] else .15, 4: tot[3] / tot[2] if tot[2] else .15,
         5: tot[5] / tot[4] if tot[4] else .15}
    obs_h = obs_b = exp_b = 0.0
    eds = nrd = 0
    for _tid, tname, nr, a3, b3, a4, b4, a5, b5 in rows:
        el = str(tname or "").lower()
        # EVERY token must appear. Half-token matching made "Classic" pool six unrelated
        # courses into what is supposed to be this course's own birdie history.
        if not all(w in el for w in toks):
            continue
        h = (a3 or 0) + (a4 or 0) + (a5 or 0)
        if not h:
            continue
        eds += 1
        nrd += nr or 0
        obs_h += h
        obs_b += (b3 or 0) + (b4 or 0) + (b5 or 0)
        exp_b += (a3 or 0) * g[3] + (a4 or 0) * g[4] + (a5 or 0) * g[5]
    if not obs_h or exp_b <= 0:
        return None, 0, 0
    raw = obs_b / exp_b
    # shrink on ROUNDS, not editions: four rounds of one edition is not a course read
    w = nrd / (nrd + 300.0)
    return max(0.75, min(1.30, 1.0 + (raw - 1.0) * w)), eds, nrd


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
        # EVERY token must appear. Half-token matching made Wyndham Championship and THE
        # PLAYERS Championship both report 57 "prior editions" of themselves with the same
        # scoring diff, because both matched on the word "Championship" — an average over
        # most of the tour, dressed up as this course's history.
        if toks and all(w in el for w in toks):
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
    # PREFER DIRECT HOLE HISTORY where we hold it (blind spot #2). The bridge is an
    # inference from scoring; counted birdies are the thing itself. Blend on rounds so one
    # thin edition cannot outvote a well-fit bridge.
    dfac, deds, dnrd = direct_course_birdie_factor(event_name)
    if dfac is not None and dnrd >= 200:
        wd = dnrd / (dnrd + 400.0)
        fac = fac * (1 - wd) + dfac * wd
        if verbose:
            print(f"  direct birdie history: {deds} edition(s), {dnrd} rounds -> "
                  f"{dfac:.3f}, blended weight {wd:.2f} -> {fac:.3f}")
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


def _espn_event_id(tname):
    """ESPN event_id for a harvested tournament name (we store these in `rounds`)."""
    con = sqlite3.connect(DB)
    like = "%" + str(tname or "")[:14].lower() + "%"
    r = con.execute("SELECT event_id, MIN(date) FROM rounds WHERE LOWER(event) LIKE ? "
                    "GROUP BY event_id ORDER BY MIN(date) DESC LIMIT 1", (like,)).fetchone()
    con.close()
    return (r[0], r[1]) if r else (None, None)


def _walk_key(o, key, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key and v:
                out.append(v)
            _walk_key(v, key, out)
    elif isinstance(o, list):
        for v in o:
            _walk_key(v, key, out)


def _course_latlon(tname, cache_key="latlon"):
    """(lat, lon) via ESPN's venue chain, then geocode the CITY.

    Geocoding the course NAME fails (geocoders index places, not courses), so we resolve
    the venue's city/state from ESPN's core API — the same chain pga_field already uses for
    the live event — and geocode that.
    """
    c = _cache()
    store = c.get(cache_key) or {}
    k = str(tname)
    if k in store:
        v = store[k]
        return (v[0], v[1]) if v else (None, None)
    eid, _d = _espn_event_id(tname)
    lat = lon = None
    if eid:
        try:
            core = json.load(urllib.request.urlopen(urllib.request.Request(
                "https://sports.core.api.espn.com/v2/sports/golf/leagues/pga/events/%s" % eid,
                headers={"User-Agent": "Mozilla/5.0"}), timeout=25))
            refs = []
            _walk_key(core, "$ref", refs)
            vref = next((str(r) for r in refs if "/venues/" in str(r)), None)
            if vref:
                ven = json.load(urllib.request.urlopen(urllib.request.Request(
                    vref.replace("http://", "https://"),
                    headers={"User-Agent": "Mozilla/5.0"}), timeout=25))
                la, lo = [], []
                _walk_key(ven, "latitude", la)
                _walk_key(ven, "longitude", lo)
                if la and lo:
                    lat, lon = float(la[0]), float(lo[0])
                else:
                    a = ven.get("address") or {}
                    city = a.get("city")
                    if city:
                        q = city + ("," + a["state"] if a.get("state") else "")
                        g = json.load(urllib.request.urlopen(urllib.request.Request(
                            "https://geocoding-api.open-meteo.com/v1/search?count=1&name="
                            + urllib.request.quote(q.split(",")[0]),
                            headers={"User-Agent": "Mozilla/5.0"}), timeout=25))
                        r0 = (g.get("results") or [{}])[0]
                        lat, lon = r0.get("latitude"), r0.get("longitude")
        except Exception:                                          # noqa: BLE001
            pass
    store[k] = [lat, lon] if lat is not None else None
    c[cache_key] = store
    _save(c)
    return lat, lon


def _archive_wind_range(lat, lon, d0, d1):
    """{date: max wind km/h} over a date range — one call covers a whole tournament week."""
    u = ("https://archive-api.open-meteo.com/v1/archive?latitude=%s&longitude=%s"
         "&start_date=%s&end_date=%s&daily=wind_speed_10m_max&timezone=UTC"
         % (lat, lon, d0, d1))
    try:
        d = json.load(urllib.request.urlopen(
            urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30))
        dd = d.get("daily") or {}
        return dict(zip(dd.get("time") or [], dd.get("wind_speed_10m_max") or []))
    except Exception:                                              # noqa: BLE001
        return {}


def fit_wind(verbose=True, refit=False):
    """WITHIN-EVENT fit of birdie rate vs wind. Demeaning inside each event removes course
    difficulty, par mix and field strength as confounders, so the surviving slope is
    weather. A non-negative slope is REJECTED (wind cannot make golf easier)."""
    c = _cache()
    if "wind" in c and not refit:
        return c["wind"]
    con = sqlite3.connect(DB)
    per = con.execute(
        "SELECT tid, tname, rnd, SUM(p3h+p4h+p5h), SUM(p3b+p4b+p5b) "
        "FROM birdie_rounds GROUP BY tid, rnd ORDER BY tid, rnd").fetchall()
    con.close()
    by_ev = {}
    for tid, tname, rnd, holes, birds in per:
        if holes and rnd and 1 <= rnd <= 4:
            by_ev.setdefault((tid, tname), []).append((rnd, birds / holes))
    xs, ys, used = [], [], 0
    for (tid, tname), rr in by_ev.items():
        if len(rr) < 3:
            continue
        lat, lon = _course_latlon(tname)
        if lat is None:
            continue
        _eid, d0 = _espn_event_id(tname)
        if not d0:
            continue
        try:
            start = dt.date.fromisoformat(d0[:10])
        except ValueError:
            continue
        wm = _archive_wind_range(lat, lon, start.isoformat(),
                                 (start + dt.timedelta(days=5)).isoformat())
        if not wm:
            continue
        pairs = []
        for rnd, rate in rr:
            day = (start + dt.timedelta(days=rnd - 1)).isoformat()
            w = wm.get(day)
            if w is not None:
                pairs.append((w, rate))
        if len(pairs) < 3:
            continue
        mw = st.mean(p[0] for p in pairs)
        mr = st.mean(p[1] for p in pairs)
        if mr <= 0:
            continue
        for w, rate in pairs:
            xs.append(w - mw)                 # within-event wind deviation
            ys.append(rate / mr - 1.0)        # within-event relative birdie deviation
        used += 1
        if verbose:
            print("     %-28s %d rounds, wind %.0f-%.0f km/h"
                  % (tname[:28], len(pairs), min(p[0] for p in pairs),
                     max(p[0] for p in pairs)))
    out = None
    if len(xs) >= 20:
        mx, my = st.mean(xs), st.mean(ys)
        den = sum((x - mx) ** 2 for x in xs)
        b = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den) if den else 0.0
        sx, sy = (st.pstdev(xs) or 1), (st.pstdev(ys) or 1)
        r = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)) / (sx * sy)
        if verbose:
            print("  WITHIN-EVENT fit: %d events, %d round-observations" % (used, len(xs)))
            print("     slope %+.5f per km/h   r=%+.3f" % (b, r))
        if b < 0:
            out = {"w": b, "n": len(xs), "events": used, "assumed": False, "r": r,
                   "design": "within-event"}
        else:
            if verbose:
                print("  REJECTED: non-negative slope -> conservative default kept")
            out = {"w": -0.003, "n": len(xs), "events": used, "assumed": True, "r": r,
                   "design": "within-event(rejected)"}
    else:
        if verbose:
            print("  fit_wind: only %d observations -> conservative default" % len(xs))
        out = {"w": -0.003, "n": len(xs), "events": used, "assumed": True}
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
