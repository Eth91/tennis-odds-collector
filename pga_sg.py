"""⛳ pga_sg — strokes-gained BY CATEGORY, free, from the PGA Tour orchestrator.

The DataGolf audit ranked "no SG decomposition" as blind spot #1: we rate players on TOTAL round
score, so a -2 earned by putting counts the same as a -2 earned by approach — yet putting is close
to noise while approach is the most persistent skill. DataGolf sells this; the PGA Tour publishes
it, through the same public orchestrator key we already use for scorecards and course stats.

statDetails(tourCode, statId, year) returns ~180 players per category per season with a per-round
average and a season total. Season-level rather than round-level, which is coarse — but it costs 6
queries per season instead of thousands, and it is the decomposition itself that was missing.

NEGATIVE RESULT 2026-07-30 — SEASON-LEVEL SG DOES NOT IMPROVE THE RULER. DO NOT WIRE IT IN.
The premise checks out: SG_OTT is the most persistent category (self-corr +0.696 Y->Y+1) and
SG_PUTT the least (+0.503), and forward power orders as expected (T2G +0.524 > APP +0.384 >
OTT +0.332 > PUTT +0.171). But the PARTIAL correlations — what each category adds ONCE this
year's SG_TOT is known — are ~zero: OTT +0.001, APP +0.016, ARG +0.044, PUTT -0.044.

Tested head-on against the ruler anyway (2026 PGA events, same test set, prior-season SG only
so there is no leakage, 77% coverage). Every variant HURT:
    blend rating toward -SG_TOT:  L=.10 -0.0017  L=.20 -0.0034  L=.50 -0.0010
    penalise putting-earned:      B=.10 -0.0024  B=.25 -0.0021  B=.50 -0.0082
Baseline 0.6048.

WHY: our rating already correlates +0.876 with SG_TOT, and it is built from ROUND-level scores
with recency weighting and a field-quality correction — finer information than a SEASON-level
aggregate. Blending in season SG adds staleness, not signal.

WHAT THIS DOES NOT RULE OUT: ROUND-level SG (scorecardStatsV3 / historicalScorecardStats) is a
different proposition and untested. Season aggregates being useless is not evidence about
per-round data. The harvest below is kept for exactly that follow-up.
"""
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

import pga_birdies as B

HERE = Path(__file__).resolve().parent
DB = HERE / "pga_model.sqlite"
D = chr(36)

# standard PGA Tour stat ids
SG_STATS = {
    "02567": "SG_OTT",       # off the tee
    "02568": "SG_APP",       # approach — the most persistent skill
    "02569": "SG_ARG",       # around the green
    "02564": "SG_PUTT",      # putting — closest to noise
    "02674": "SG_T2G",       # tee to green
    "02675": "SG_TOT",       # total
}

DDL = """CREATE TABLE IF NOT EXISTS sg_stats(
    tour TEXT, year INTEGER, stat TEXT, player_id TEXT, player TEXT,
    avg REAL, total REAL, rounds REAL, fetched TEXT,
    PRIMARY KEY(tour, year, stat, player_id))"""

Q = ('query SD(%st: TourCode!, %ss: String!, %sy: Int!) '
     '{statDetails(tourCode: %st, statId: %ss, year: %sy) '
     '{statTitle rows {... on StatDetailsPlayer {playerId playerName '
     'stats {statName statValue}}}}}' % (D, D, D, D, D, D))


def _num(x):
    try:
        return float(str(x).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def harvest(years=(2023, 2024, 2025, 2026), tour="R", verbose=True):
    con = sqlite3.connect(DB)
    con.execute(DDL)
    con.commit()
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    total = 0
    for yr in years:
        for sid, label in SG_STATS.items():
            try:
                d = B.gql(Q, {"t": tour, "s": sid, "y": int(yr)})
            except Exception as e:                                  # noqa: BLE001
                if verbose:
                    print("   %s %s %s: %s" % (tour, yr, label, str(e)[:50]))
                continue
            if d.get("errors"):
                if verbose:
                    print("   %s %s %s: %s" % (tour, yr, label, str(d["errors"])[:60]))
                continue
            sd = (d.get("data") or {}).get("statDetails") or {}
            rows = []
            for r in sd.get("rows") or []:
                pid, pname = r.get("playerId"), r.get("playerName")
                if not pid:
                    continue
                vals = {s.get("statName"): s.get("statValue") for s in (r.get("stats") or [])}
                avg = _num(vals.get("Avg"))
                tot = next((_num(v) for k, v in vals.items()
                            if k and k.lower().startswith("total")), None)
                rnds = next((_num(v) for k, v in vals.items()
                             if k and "round" in k.lower()), None)
                if avg is None and tot is None:
                    continue
                rows.append((tour, int(yr), label, str(pid), pname, avg, tot, rnds, now))
            if rows:
                con.executemany(
                    "INSERT OR REPLACE INTO sg_stats VALUES (?,?,?,?,?,?,?,?,?)", rows)
                con.commit()
                total += len(rows)
                if verbose:
                    print("   %s %d %-8s %4d players" % (tour, yr, label, len(rows)))
    n = con.execute("SELECT COUNT(*), COUNT(DISTINCT player_id) FROM sg_stats").fetchone()
    con.close()
    if verbose:
        print("  sg_stats: %d rows over %d players (+%d this run)" % (n[0], n[1], total))
    return n


def player_sg(years=None, half_life_y=1.5):
    """{norm(player): {stat: recency-weighted avg}} — the model-facing view.

    Weighted across seasons because a player's approach skill two years ago still says something,
    just less. Half-life in YEARS since SG here is season-level.
    """
    import pga_ruler as RU
    con = sqlite3.connect(DB)
    con.execute(DDL)
    rows = con.execute("SELECT year, stat, player, avg FROM sg_stats "
                       "WHERE avg IS NOT NULL").fetchall()
    con.close()
    if not rows:
        return {}
    cur = max(r[0] for r in rows)
    acc = {}
    for yr, stat, player, avg in rows:
        if years and yr not in years:
            continue
        w = 0.5 ** ((cur - yr) / float(half_life_y))
        d = acc.setdefault(RU.norm(player), {}).setdefault(stat, [0.0, 0.0])
        d[0] += avg * w
        d[1] += w
    return {p: {s: (v[0] / v[1]) for s, v in d.items() if v[1] > 0} for p, d in acc.items()}


if __name__ == "__main__":
    yrs = tuple(int(a) for a in sys.argv[1:] if a.isdigit()) or (2023, 2024, 2025, 2026)
    harvest(years=yrs)
    sg = player_sg()
    print("  player_sg(): %d players" % len(sg))
    top = sorted(sg.items(), key=lambda kv: -(kv[1].get("SG_APP") or -9))[:5]
    for p, d in top:
        print("     %-24s APP %+.3f  OTT %+.3f  PUTT %+.3f  TOT %+.3f"
              % (p, d.get("SG_APP", 0), d.get("SG_OTT", 0), d.get("SG_PUTT", 0),
                 d.get("SG_TOT", 0)))
