"""Apply the DvP filter to the 33-15 record. LEAK-FREE: DvP is refit as of each bet's own date.

THE FILTER, taken from dvp_backtest's own split: an over into a positional defence whose coefficient
is strongly NEGATIVE (tough) is the losing cell — 14-17 / 45.2% there versus 27-12 / 69.2% into a
soft one. Candidate rule: DROP an over when coef <= -THRESH.

WHY REFIT PER DATE. wnba_dvp's cached table is computed from the CURRENT season, so scoring a bet
from 2026-07-09 with it would use games that had not happened yet — the same look-ahead that made
the n_without buckets meaningless until they were computed as-of. Here DvP is refit on player-games
strictly BEFORE each bet's date, reusing dvp_backtest.fit_dvp so the estimator is identical to the
one that produced the 69.2/45.2 split.

Reported at several thresholds, because a filter that only looks good at one hand-picked cutoff is
a hand-picked cutoff. Volume cost is shown alongside, since WNBA optimises TOTAL UNITS.
"""
import random
import sqlite3
from collections import defaultdict

import numpy as np

import dvp_backtest as D
import wnba_slip as SL
import wnba_wowy as W

BET_ROLES = {"confirmed", "likely"}
STAT2K = {"points": "pts", "rebounds": "reb", "assists": "ast"}

# ── the record as the board counts it ─────────────────────────────────────────
con = sqlite3.connect("wnba_ledger.sqlite")
cols = [d[1] for d in con.execute("PRAGMA table_info(predictions)")]
g = [dict(zip(cols, r)) for r in con.execute("SELECT * FROM predictions WHERE graded=1")]
con.close()
overs = [r for r in g if r["result"] in ("over", "under") and (r["side"] or "over") == "over"
         and (r.get("tier") or "firm") != "n1"]
dec, _ = SL.current_selection(overs)
BASE = [r for r in dec if str(r.get("confidence")) in BET_ROLES or r.get("played")]
print("  base record universe: %d bets" % len(BASE))

# ── build the player-game history once, then refit per date ───────────────────
print("  building boxscore history (this is the slow part)...", flush=True)
hist, allg = D.build(60)
print("  %d player-games across %d dates" % (len(allg), len({x["date"] for x in allg})))
pos = D.positions()
lg_pace = np.mean([x["poss"] for x in allg if x.get("poss")]) if allg else 83.2

_fit_cache = {}


def coef_asof(date, team, position, statk):
    """Opponent-adjusted DvP for `team` vs `position` on `statk`, fit ONLY on games before `date`."""
    key = (date, statk, D._PG.get(position, position))
    if key in _fit_cache:
        return _fit_cache[key].get(team)
    pg = D._PG.get(position, position)
    rows = []
    for x in allg:
        if x["date"] >= date:
            continue                                  # strictly prior games only
        if (x.get("min") or 0) < D.MIN_MIN:
            continue
        if D._PG.get(pos.get(x["pid"]), None) != pg:
            continue
        poss = x.get("poss") or lg_pace
        rate = (x.get(statk) or 0) / max(x["min"], 1e-9) * (lg_pace / max(poss, 1e-9))
        rows.append((x["pid"], x["opp"], rate))
    adj, _naive = D.fit_dvp(rows, lg_pace)
    _fit_cache[key] = adj
    return adj.get(team)


players = W.players() or {}
resolved = 0
for r in BASE:
    p = players.get(r.get("player")) or {}
    statk = STAT2K.get(r.get("stat"))
    c = None
    if statk and r.get("opp") and p.get("position"):
        try:
            c = coef_asof(str(r["pred_date"])[:10], r["opp"], p["position"], statk)
        except Exception:                                          # noqa: BLE001
            c = None
    r["_dvp"] = c
    resolved += c is not None
print("  DvP resolved as-of date for %d of %d bets" % (resolved, len(BASE)))


def won(r):
    return r["result"] == (r["side"] or "over")


def ret(r):
    return (float(r.get("odds") or 0) - 1) if won(r) else -1.0


def boot(rows, iters=2000):
    byd = defaultdict(list)
    for r in rows:
        byd[str(r.get("pred_date"))[:10]].append(ret(r))
    ks = list(byd)
    if len(ks) < 2:
        return None
    rng = random.Random(7)
    s = []
    for _ in range(iters):
        v = [x for k in rng.choices(ks, k=len(ks)) for x in byd[k]]
        if v:
            s.append(sum(v) / len(v))
    s.sort()
    return s[int(.025 * len(s))], s[int(.975 * len(s))]


def show(lab, rows, base=None):
    n = len(rows)
    if not n:
        print("  %-30s (none)" % lab)
        return None
    w = sum(1 for r in rows if won(r))
    u = sum(ret(r) for r in rows)
    ci = boot(rows)
    d = "" if base is None else "   (%+d bets, %+.2fu)" % (n - base[0], u - base[1])
    print("  %-30s %3d %2d-%-2d %6.1f%% %+8.2fu %+7.1f%%  %s%s"
          % (lab, n, w, n - w, 100 * w / n, u, 100 * u / n,
             ("CI %+.0f%%..%+.0f%%" % (100 * ci[0], 100 * ci[1])) if ci else "CI n/a", d))
    return (n, u)


print("\n  %-30s %3s %6s %7s %9s %8s" % ("variant", "n", "record", "hit%", "units", "ROI"))
b = show("BOARD TODAY (33-15)", BASE)
for th in (0.005, 0.010, 0.015, 0.020):
    keep = [r for r in BASE if r.get("_dvp") is None or r["_dvp"] > -th]
    show("drop overs with coef <= -%.3f" % th, keep, b)

print("\n=== the split the filter is built on, on OUR OWN bets ===")
for lab, sel in (("into SOFT D  (coef >= +0.010)", lambda c: c is not None and c >= 0.010),
                 ("neutral      (|coef| < 0.010)", lambda c: c is not None and abs(c) < 0.010),
                 ("into TOUGH D (coef <= -0.010)", lambda c: c is not None and c <= -0.010),
                 ("unresolved", lambda c: c is None)):
    show(lab, [r for r in BASE if sel(r.get("_dvp"))])
print("\n  dvp_backtest's own universe gave 69.2%% soft vs 45.2%% tough (n=70). If our carded bets")
print("  show the same ordering the filter transfers; if not, it was measuring a different pool.")
