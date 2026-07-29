"""⛳ pga_wave — tee sheets from the PGA orchestrator, and a FITTED wave effect.

Fixes the two separate things the 2026-07-29 audit called blind about waves:

  SOURCE   The wave path was dormant because tee times came from ESPN, which only stamps
           teeTime on a competitor once that round is essentially underway. The
           orchestrator publishes the whole tee sheet DAYS earlier — 294 entries for the
           Rocket Classic while ESPN still showed 0. Reading the orchestrator makes the
           wave path live, and live EARLIER, which is the same speed edge the WNBA loop
           is built around.

  FITTED   wave_shift was a wind-exposure heuristic (a comment literally said "0.5-1.5
           strokes for a real wave split, which this reproduces"). fit_wave() measures the
           actual AM-vs-PM stroke gap WITHIN each event-round, so course difficulty, field
           strength and par mix all cancel by construction, and it reports its own n, sd
           and r. The live shift becomes a measured relationship instead of an assumption.

The discipline from fit_wind carries over: a fit that is too thin or too weak is REJECTED
and flagged assumed=True rather than quietly shipping a number nobody measured.
"""
import datetime as dt
import json
import math
import sqlite3
import statistics as st
import time
import urllib.request
from pathlib import Path

import pga_birdies as B
import pga_context as C
import pga_ruler as RU

HERE = Path(__file__).resolve().parent
DB = HERE / "pga_model.sqlite"          # read-only here: rounds / birdie_rounds live in it
TEEDB = HERE / "pga_tees.sqlite"        # our own, gitignored: never in the reset/replay race
UA = {"User-Agent": "Mozilla/5.0"}

D = chr(36)                       # keep '$' out of any shell that transports this file
SPLIT_MIN = 20                    # min players per wave for an event-round to count
FIT_MIN_OBS = 20                  # min event-rounds before a fitted beta is trusted
EXPOSURE_H = 5                    # hours of play used for a wave's wind exposure

DDL = """CREATE TABLE IF NOT EXISTS tee_sheet(
    tid TEXT, tname TEXT, rnd INTEGER, player TEXT, tee_ms INTEGER, start_tee INTEGER,
    tz TEXT, PRIMARY KEY(tid, rnd, player))"""

TEE_Q = ('query T(%st: ID!) {teeTimes(id: %st) {timezone rounds {roundInt groups '
         '{teeTime startTee players {firstName lastName}}}}}' % (D, D))


# --------------------------------------------------------------------- harvest
def fetch_sheet(tid):
    """[(rnd, player_norm, tee_ms, start_tee)], tz  for one tournament id."""
    d = B.gql(TEE_Q, {"t": tid})
    tt = ((d.get("data") or {}).get("teeTimes") or {})
    out = []
    for r in tt.get("rounds") or []:
        rnd = r.get("roundInt")
        if not rnd:
            continue
        for g in r.get("groups") or []:
            ms = g.get("teeTime")
            if not ms:
                continue
            for p in g.get("players") or []:
                nm = RU.norm("%s %s" % (p.get("firstName") or "", p.get("lastName") or ""))
                if nm:
                    out.append((int(rnd), nm, int(ms), g.get("startTee")))
    return out, (tt.get("timezone") or "UTC")


def harvest_tees(tids=None, years=(2024, 2025, 2026), verbose=True):
    """Store tee sheets. Idempotent: an event already stored is skipped, so this is safe to
    call from the loop. Historical sheets are what make fit_wave possible at all."""
    con = sqlite3.connect(TEEDB, timeout=30)
    con.execute(DDL)
    con.commit()
    have = {r[0] for r in con.execute("SELECT DISTINCT tid FROM tee_sheet").fetchall()}
    if tids is None:
        tids = []
        for yr in years:
            for tid, tname in B.completed_tournaments(year=yr):
                tids.append((tid, tname))
        for tid, tname in B.upcoming_tournaments():
            tids.append((tid, tname))
    else:
        tids = [(t, "") if isinstance(t, str) else t for t in tids]
    new = 0
    for tid, tname in tids:
        if tid in have and not str(tid).startswith("R2026"):
            continue                                  # past sheets never change; 2026 can
        try:
            rows, tz = fetch_sheet(tid)
        except Exception as e:                                      # noqa: BLE001
            if verbose:
                print("   %s fetch failed: %s" % (tid, str(e)[:60]))
            continue
        if not rows:
            continue
        payload = [(tid, tname, rnd, nm, ms, stee, tz) for rnd, nm, ms, stee in rows]
        for attempt in range(6):
            try:
                con.executemany(
                    "INSERT OR REPLACE INTO tee_sheet(tid,tname,rnd,player,tee_ms,"
                    "start_tee,tz) VALUES(?,?,?,?,?,?,?)", payload)
                con.commit()
                break
            except sqlite3.OperationalError as e:      # reset window: reconnect and retry
                if attempt == 5:
                    raise
                if verbose:
                    print("   %s write retry %d (%s)" % (tid, attempt + 1, str(e)[:40]))
                time.sleep(2.0 * (attempt + 1))
                try:
                    con.close()
                except Exception:                                   # noqa: BLE001
                    pass
                con = sqlite3.connect(TEEDB, timeout=30)
                con.execute(DDL)
        new += 1
        if verbose:
            print("   %-10s %-30s %d tee rows" % (tid, str(tname)[:30], len(rows)))
    tot = con.execute("SELECT COUNT(*), COUNT(DISTINCT tid) FROM tee_sheet").fetchone()
    con.close()
    if verbose:
        print("  tee_sheet: %d rows over %d events (+%d new)" % (tot[0], tot[1], new))
    return tot


# ----------------------------------------------------------------- live access
def tees_for(tid, rnd=None):
    """{player_norm: tee_ms} for one round. Orchestrator-backed, so this is populated days
    before ESPN's competitor stamp — the reason the wave path is no longer dormant."""
    con = sqlite3.connect(TEEDB, timeout=30)
    con.execute(DDL)
    if rnd is None:
        r = con.execute("SELECT MIN(rnd) FROM tee_sheet WHERE tid=?", (tid,)).fetchone()
        rnd = (r or [1])[0] or 1
    rows = con.execute("SELECT player, tee_ms FROM tee_sheet WHERE tid=? AND rnd=?",
                       (tid, rnd)).fetchall()
    con.close()
    return dict(rows)


def waves(tid, rnd=None, tees=None):
    """{player_norm: 'am'|'pm'} by the median tee time of that round's own sheet."""
    tees = tees if tees is not None else tees_for(tid, rnd)
    if len(tees) < 2 * SPLIT_MIN:
        return {}
    med = st.median(tees.values())
    return {p: ("pm" if t > med else "am") for p, t in tees.items()}


# ------------------------------------------------------------------ wind hourly
def _wind_hourly(lat, lon, d0, d1):
    """{iso_hour: wind km/h} — one archive call covers a whole tournament week."""
    u = ("https://archive-api.open-meteo.com/v1/archive?latitude=%s&longitude=%s"
         "&start_date=%s&end_date=%s&hourly=wind_speed_10m&timezone=UTC" % (lat, lon, d0, d1))
    try:
        d = json.load(urllib.request.urlopen(
            urllib.request.Request(u, headers=UA), timeout=30))
        h = d.get("hourly") or {}
        return dict(zip(h.get("time") or [], h.get("wind_speed_10m") or []))
    except Exception:                                               # noqa: BLE001
        return {}


def _exposure(wind_h, tee_ms):
    """Mean wind over the EXPOSURE_H hours a group is actually on the course."""
    if not tee_ms:
        return None
    t0 = dt.datetime.fromtimestamp(tee_ms / 1000.0, dt.timezone.utc)
    vals = []
    for i in range(EXPOSURE_H):
        k = (t0 + dt.timedelta(hours=i)).strftime("%Y-%m-%dT%H:00")
        v = wind_h.get(k)
        if v is not None:
            vals.append(v)
    return st.mean(vals) if vals else None


# ------------------------------------------------------------------ the fit
def _rel_scores():
    """{(event_id, rnd): {player_norm: strokes - that round's field mean}}"""
    con = sqlite3.connect(DB)
    raw = {}
    for eid, rnd, pl, sc in con.execute(
            "SELECT event_id, rnd, player, score FROM rounds WHERE score > 0"):
        raw.setdefault((eid, rnd), {})[RU.norm(pl)] = sc
    con.close()
    out = {}
    for k, d in raw.items():
        if len(d) < 2 * SPLIT_MIN:
            continue
        m = st.mean(d.values())
        out[k] = {p: s - m for p, s in d.items()}
    return out


def _event_ids():
    """[(event_id, first_date, event_name)] for date+name matching against tids."""
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT event_id, MIN(date), event FROM rounds GROUP BY event_id"
                       ).fetchall()
    con.close()
    return rows


def _match_event(tname, r1_ms, tz, evs):
    """Resolve an orchestrator tid to the ESPN event_id holding its SCORES.

    Name alone is ambiguous across editions and date alone collides with opposite-field
    events the same week, so both are required.
    """
    try:
        from zoneinfo import ZoneInfo
        day = dt.datetime.fromtimestamp(r1_ms / 1000.0, ZoneInfo(tz)).date()
    except Exception:                                               # noqa: BLE001
        day = dt.datetime.fromtimestamp(r1_ms / 1000.0, dt.timezone.utc).date()
    toks = [t.lower() for t in str(tname or "").split() if len(t) > 3]
    best = None
    for eid, d0, evn in evs:
        if not d0:
            continue
        try:
            ed = dt.date.fromisoformat(str(d0)[:10])
        except ValueError:
            continue
        gap = abs((ed - day).days)
        if gap > 3:
            continue
        el = str(evn or "").lower()
        if toks and not any(t in el for t in toks):
            continue
        if best is None or gap < best[1]:
            best = (eid, gap)
    return best[0] if best else None


def fit_wave(verbose=True, refit=False):
    """WITHIN-EVENT-ROUND fit of the AM/PM stroke gap against the wave wind-exposure gap.

    Demeaning inside an event-round removes course, field and par mix as confounders, so
    the surviving gap is tee-window: wind, and whatever else systematically separates the
    two waves (greens firming, morning dew, afternoon thunderstorm holds).

    Returns beta (strokes per km/h of exposure gap), the raw gap distribution, and n.
    """
    c = C._cache()
    if "wave" in c and not refit:
        return c["wave"]
    rel = _rel_scores()
    evs = _event_ids()
    con = sqlite3.connect(TEEDB, timeout=30)
    con.execute(DDL)
    sheets = {}
    for tid, tname, rnd, pl, ms, tz in con.execute(
            "SELECT tid, tname, rnd, player, tee_ms, tz FROM tee_sheet"):
        sheets.setdefault((tid, tname, tz), {}).setdefault(rnd, {})[pl] = ms
    con.close()

    xs, ys, gaps, used_ev = [], [], [], set()
    for (tid, tname, tz), by_rnd in sorted(sheets.items()):
        r1 = by_rnd.get(1) or {}
        if not r1:
            continue
        eid = _match_event(tname, min(r1.values()), tz, evs)
        if not eid:
            continue
        lat, lon = C._course_latlon(tname)
        wind_h = {}
        if lat is not None:
            days = sorted({dt.datetime.fromtimestamp(m / 1000.0, dt.timezone.utc).date()
                           for d in by_rnd.values() for m in d.values()})
            if days:
                wind_h = _wind_hourly(lat, lon, days[0].isoformat(), days[-1].isoformat())
        for rnd, tees in sorted(by_rnd.items()):
            sc = rel.get((eid, rnd))
            if not sc:
                continue
            med = st.median(tees.values())
            am = [(p, t) for p, t in tees.items() if t <= med]
            pm = [(p, t) for p, t in tees.items() if t > med]
            a_s = [sc[p] for p, _t in am if p in sc]
            p_s = [sc[p] for p, _t in pm if p in sc]
            if len(a_s) < SPLIT_MIN or len(p_s) < SPLIT_MIN:
                continue
            gap = st.mean(p_s) - st.mean(a_s)          # + = PM played harder
            gaps.append((tname, rnd, gap, len(a_s), len(p_s)))
            used_ev.add(tid)
            if wind_h:
                ea = [_exposure(wind_h, t) for _p, t in am]
                ep = [_exposure(wind_h, t) for _p, t in pm]
                ea = [v for v in ea if v is not None]
                ep = [v for v in ep if v is not None]
                if ea and ep:
                    xs.append(st.mean(ep) - st.mean(ea))
                    ys.append(gap)

    out = {"n_gaps": len(gaps), "events": len(used_ev), "n_wind": len(xs)}
    if gaps:
        g = [x[2] for x in gaps]
        out["mean_gap"] = st.mean(g)
        out["sd_gap"] = st.pstdev(g) if len(g) > 1 else 0.0
        out["mean_abs_gap"] = st.mean([abs(v) for v in g])
    if len(xs) >= FIT_MIN_OBS:
        mx, my = st.mean(xs), st.mean(ys)
        den = sum((x - mx) ** 2 for x in xs)
        b = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den) if den else 0.0
        sx = st.pstdev(xs) or 1
        sy = st.pstdev(ys) or 1
        r = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)) / (sx * sy)
        a = my - b * mx
        if b > 0:                                      # windier wave must score WORSE
            out.update({"beta": b, "intercept": a, "r": r, "assumed": False,
                        "design": "within-event-round"})
        else:
            out.update({"beta": 0.02, "intercept": 0.0, "r": r, "assumed": True,
                        "design": "within-event-round(rejected: beta<=0)"})
    else:
        out.update({"beta": 0.02, "intercept": 0.0, "r": None, "assumed": True,
                    "design": "insufficient-wind-obs"})
    if verbose:
        print("  wave gaps: n=%d event-rounds over %d events" % (out["n_gaps"], out["events"]))
        if gaps:
            print("     mean PM-AM gap %+.3f str   sd %.3f   mean |gap| %.3f"
                  % (out["mean_gap"], out["sd_gap"], out["mean_abs_gap"]))
            for tname, rnd, gap, na, npm in sorted(gaps, key=lambda z: -abs(z[2]))[:5]:
                print("     %-26s R%d  %+.2f str  (%d am / %d pm)"
                      % (str(tname)[:26], rnd, gap, na, npm))
        print("     beta %+.4f str per km/h exposure gap  r=%s  n_wind=%d  %s"
              % (out["beta"], ("%+.3f" % out["r"]) if out.get("r") is not None else "n/a",
                 out["n_wind"], "ASSUMED" if out.get("assumed") else "FITTED"))
    c["wave"] = out
    C._save(c)
    return out


def wave_shift_for(tid, rnd=None, lat=None, lon=None, day=None, verbose=False):
    """Live wave shift in STROKES for this round's actual tee sheet and forecast wind.

    Uses the fitted beta on the real exposure gap between the two waves. Returns
    (wave_map, shift_strokes, note) with an empty map when the sheet is not out yet.
    """
    tees = tees_for(tid, rnd)
    wv = waves(tid, rnd, tees=tees)
    if not wv:
        return {}, 0.0, "tee sheet not posted"
    f = fit_wave(verbose=False)
    days = sorted({dt.datetime.fromtimestamp(m / 1000.0, dt.timezone.utc).date()
                   for m in tees.values()})
    if lat is None or lon is None or not days:
        return wv, 0.0, "wave split known, no coords for exposure"
    wind_h = _wind_hourly(lat, lon, days[0].isoformat(), days[-1].isoformat())
    if not wind_h:
        return wv, 0.0, "wave split known, wind unavailable"
    ea = [_exposure(wind_h, t) for p, t in tees.items() if wv.get(p) == "am"]
    ep = [_exposure(wind_h, t) for p, t in tees.items() if wv.get(p) == "pm"]
    ea = [v for v in ea if v is not None]
    ep = [v for v in ep if v is not None]
    if not ea or not ep:
        return wv, 0.0, "wave split known, exposure unavailable"
    xgap = st.mean(ep) - st.mean(ea)
    shift = f.get("beta", 0.02) * xgap + f.get("intercept", 0.0)
    # a wave edge larger than the sd of every gap we have ever measured is not credible
    cap = max(1.5, 2.0 * (f.get("sd_gap") or 0.5))
    shift = max(-cap, min(cap, shift))
    note = "exposure gap %+.1f km/h -> %+.2f str%s" % (
        xgap, shift, " (assumed beta)" if f.get("assumed") else "")
    if verbose:
        print("   " + note)
    return wv, shift, note


if __name__ == "__main__":
    import sys
    if "--harvest" in sys.argv:
        harvest_tees()
    fit_wave(verbose=True, refit="--refit" in sys.argv)
