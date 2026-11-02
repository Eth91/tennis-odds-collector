#!/usr/bin/env python3
"""NHL_SOG_PREREG.md: an NHL shots-on-goal model (ice time by strength x shot-attempt rate by strength x on-target share
x the opponent) against the plain per-game average and the book near puck drop. Mac only.

    python3 nhl_sog.py --pull     # the NHL stats reports, 2022-23 to 2025-26 -> .projdata/nhl_sog.sqlite (resumable)
    python3 nhl_sog.py            # the tests
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import math
import re
import sqlite3
import ssl
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from scipy import stats as st
from scipy.special import gammaln

HERE = Path(__file__).resolve().parent
STORE = HERE / ".projdata" / "nhl_sog.sqlite"
OUT = HERE / ".projdata" / "nhl_sog_result.json"
ODDS = Path.home() / "tennis-odds-collector" / "icehockey_nhl_odds_hist.sqlite"
REST = "https://api.nhle.com/stats/rest/en"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
ET = ZoneInfo("America/New_York")
SEASONS, FIT, TEST = (2022, 2023, 2024, 2025), 2023, (2024, 2025)
LAST_AS, MIN_GAMES = 20.0, 3                 # last season worth at most 20 games; 3+ games across the two
STR = ("ev", "pp", "sh")
K_HOURS = {"ev": 3.0, "pp": 1.0, "sh": 1.0}  # the attempt-rate shrink, in hours of ice time
K_OT, OPP_PULL, EV_MIN = 60.0, 0.5, 0.05
RATIO_AT, PING_LO, PING_HI, PRICE_MIN = 0.80, 0.50, 0.70, 1 / 0.6
FRANCHISE = {"ARI": "UTA"}                   # Arizona's 2023-24 is Utah's last season
REPORTS = {   # report: (table, {column: field}); skater tables keyed (gid, pid), the team table (gid, team id)
    "skater/summary": ("sk", {"date": "gameDate", "team": "teamAbbrev", "opp": "opponentTeamAbbrev", "pos": "positionCode",
                              "name": "skaterFullName", "shots": "shots", "toi": "timeOnIcePerGame"}),
    "skater/realtime": ("rt", {"att": "totalShotAttempts", "missed": "missedShots", "blocked": "shotAttemptsBlocked"}),
    "skater/timeonice": ("ti", {"ev": "evTimeOnIce", "pp": "ppTimeOnIce", "sh": "shTimeOnIce"}),
    "skater/powerplay": ("pp", {"shots": "ppShots", "att": "ppIndividualSatFor"}),
    "skater/penaltykill": ("pk", {"shots": "shShots", "att": "shIndividualSatFor"}),
    "team/summary": ("tm", {"date": "gameDate", "name": "teamFullName", "opp": "opponentTeamAbbrev",
                            "sf": "shotsForPerGame", "sa": "shotsAgainstPerGame"}),
}
rng = np.random.default_rng(5)


# ---- the pull ----------------------------------------------------------------------------------------------------
def fetch(url, tries=4):
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120,
                                        context=ctx) as r:
                return json.load(r)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def windows(season):
    """15-day [from, to) windows from 20 Sep to 1 Jul: a fortnight is about 4,000 player-games (a report answers 10,000)."""
    d, end = dt.date(season, 9, 20), dt.date(season + 1, 7, 1)
    while d < end:
        yield d.isoformat(), min(d + dt.timedelta(days=15), end).isoformat()
        d += dt.timedelta(days=15)


def pull():
    STORE.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(STORE)
    for t, cols in REPORTS.values():
        k2 = "team_id" if t == "tm" else "pid"
        con.execute(f"CREATE TABLE IF NOT EXISTS {t} (gid INTEGER, {k2} INTEGER, {', '.join(cols)}, PRIMARY KEY (gid, {k2}))")
    con.execute("CREATE TABLE IF NOT EXISTS done (ref TEXT PRIMARY KEY, n INTEGER)")
    have = {r for (r,) in con.execute("SELECT ref FROM done")}
    for s in SEASONS:
        for a, b in windows(s):
            for rep, (t, cols) in REPORTS.items():
                ref = f"{rep}|{s}|{a}"
                if ref in have:
                    continue
                cay = f'seasonId={s}{s + 1} and gameTypeId>=2 and gameDate>="{a}" and gameDate<"{b}"'
                d = fetch(f"{REST}/{rep}?isAggregate=false&isGame=true&start=0&limit=-1&cayenneExp=" + urllib.parse.quote(cay))
                rows = d.get("data") or []
                if len(rows) < (d.get("total") or 0) or len(rows) >= 10000:
                    raise SystemExit(f"{ref}: {len(rows)} of {d.get('total')} rows: the window is too wide")
                k2 = "teamId" if t == "tm" else "playerId"
                con.executemany(f"INSERT OR REPLACE INTO {t} VALUES ({','.join('?' * (2 + len(cols)))})",
                                [(r["gameId"], r[k2], *[r.get(f) for f in cols.values()]) for r in rows])
                con.execute("INSERT INTO done VALUES (?, ?)", (ref, len(rows)))
                con.commit()
                print(f"{ref}: {len(rows)}", flush=True)
                time.sleep(0.3)
    con.close()


# ---- the store ---------------------------------------------------------------------------------------------------
def fold(name):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower().replace("-", " ")
    s = re.sub(r"[^a-z ]", "", s)
    return re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", re.sub(r"\s+", " ", s).strip())


def team(code):
    return FRANCHISE.get(code, code)


def group(pos):
    return "D" if pos == "D" else "F"


def load(store=STORE):
    """(player-games by pid in date order, {gid: (date, {team: opp})}, team-games {team: [(date, season, sa)]},
    {folded team name: team})."""
    con = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    q = ("SELECT sk.gid, sk.pid, sk.date, sk.team, sk.opp, sk.pos, sk.name, sk.shots, sk.toi, rt.att, ti.ev, ti.pp, ti.sh, "
         "pp.shots, pp.att, pk.shots, pk.att FROM sk LEFT JOIN rt USING (gid, pid) LEFT JOIN ti USING (gid, pid) "
         "LEFT JOIN pp USING (gid, pid) LEFT JOIN pk USING (gid, pid)")
    by_pid, games = defaultdict(list), {}
    for gid, pid, date, tm, opp, pos, name, shots, toi, att, ev, pp, sh, pps, ppa, shs, sha in con.execute(q):
        shots, pps, ppa, shs, sha = shots or 0, pps or 0, ppa or 0, shs or 0, sha or 0
        att = max(att if att is not None else shots, shots)
        if ev is None:                                        # no time-on-ice row: all of it at even strength
            ev, pp, sh = toi or 0, 0, 0
        g = {"gid": gid, "pid": pid, "date": date, "season": gid // 1000000, "po": (gid // 10000) % 100 == 3,
             "team": team(tm), "opp": team(opp), "grp": group(pos), "name": name, "shots": shots, "att": att,
             "att_pp": ppa, "att_sh": sha, "att_ev": max(0, att - ppa - sha),
             "sog_pp": pps, "sog_sh": shs, "sog_ev": max(0, shots - pps - shs),
             "min_ev": (ev or 0) / 60, "min_pp": (pp or 0) / 60, "min_sh": (sh or 0) / 60}
        by_pid[pid].append(g)
        games.setdefault(gid, (date, {}))[1][g["team"]] = g["opp"]
    for v in by_pid.values():
        v.sort(key=lambda g: (g["date"], g["gid"]))
    tg, names = defaultdict(list), {}
    for gid, name, opp, sa, date in con.execute("SELECT gid, name, opp, sa, date FROM tm"):
        teams = games.get(gid, (None, {}))[1]
        mine = [t for t, o in teams.items() if o == team(opp)]
        if len(mine) == 1 and sa is not None:
            tg[mine[0]].append((date, gid // 1000000, float(sa)))
            names[fold(name)] = mine[0]
    for v in tg.values():
        v.sort()
    con.close()
    return by_pid, games, tg, names


# ---- the model ---------------------------------------------------------------------------------------------------
SUMS = ("shots", "att", "att_ev", "att_pp", "att_sh", "sog_ev", "sog_pp", "sog_sh", "min_ev", "min_pp", "min_sh")


def history(games):
    """[(game, features or None)]: each game's features from his games before its date only (this season and last)."""
    cum = defaultdict(lambda: dict.fromkeys(SUMS + ("n",), 0.0))
    recent, out, i = deque(maxlen=5), [], 0
    while i < len(games):
        j = i
        while j < len(games) and games[j]["date"] == games[i]["date"]:
            j += 1
        for g in games[i:j]:                                  # a same-day game is never history
            this, last = cum[g["season"]], cum[g["season"] - 1]
            nt, nl = this["n"], last["n"]
            f = None
            if nt + nl >= MIN_GAMES and recent:
                w = min(1.0, LAST_AS / nl) if nl else 0.0
                W = {k: this[k] + w * last[k] for k in SUMS}
                Wn = nt + w * nl
                f = {"W": W, "Wn": Wn, "avg": W["shots"] / Wn}
                for k in STR:
                    f[f"last1_{k}"] = recent[-1][f"min_{k}"]
                    f[f"last5_{k}"] = sum(r[f"min_{k}"] for r in recent) / len(recent)
                    f[f"mean_{k}"] = W[f"min_{k}"] / Wn
            out.append((g, f))
        for g in games[i:j]:
            c = cum[g["season"]]
            for k in SUMS:
                c[k] += g[k]
            c["n"] += 1
            recent.append(g)
        i = j
    return out


def priors(by_pid, season=FIT):
    """{group: {"att_ev": per hour, ..., "sog_ev": per hour, ..., "ot": shots per attempt}} over a season's games."""
    tot = defaultdict(lambda: defaultdict(float))
    for gl in by_pid.values():
        for g in gl:
            if g["season"] == season:
                t = tot[g["grp"]]
                for k in SUMS:
                    t[k] += g[k]
    out = {}
    for grp, t in tot.items():
        p = {"ot": t["shots"] / t["att"]}
        for k in STR:
            p[f"att_{k}"] = t[f"att_{k}"] / (t[f"min_{k}"] / 60)
            p[f"sog_{k}"] = t[f"sog_{k}"] / (t[f"min_{k}"] / 60)
        out[grp] = p
    return out


def rates(f, grp, pri):
    """(attempts per hour by strength, on-target share, shots on goal per hour by strength), shrunk to the group's priors."""
    W, p = f["W"], pri[grp]
    att = {k: (W[f"att_{k}"] + K_HOURS[k] * p[f"att_{k}"]) / (W[f"min_{k}"] / 60 + K_HOURS[k]) for k in STR}
    sog = {k: (W[f"sog_{k}"] + K_HOURS[k] * p[f"sog_{k}"]) / (W[f"min_{k}"] / 60 + K_HOURS[k]) for k in STR}
    return att, (W["shots"] + K_OT * p["ot"]) / (W["att"] + K_OT), sog


def toi_fit(recs):
    """{strength: OLS beta} on the fit season's player-games: minutes ~ 1 + last game + last 5 + weighted season mean."""
    out = {}
    for k in STR:
        X = np.array([[1, f[f"last1_{k}"], f[f"last5_{k}"], f[f"mean_{k}"]] for g, f in recs])
        y = np.array([g[f"min_{k}"] for g, f in recs])
        out[k] = np.linalg.lstsq(X, y, rcond=None)[0]
    return out


def toi_proj(f, beta):
    return {k: max(0.0, float(beta[k] @ [1, f[f"last1_{k}"], f[f"last5_{k}"], f[f"mean_{k}"]])) for k in STR}


class Opp:
    """The opponent factor: his shots against per game (this season before the date, last season as 20 games) over all
    teams' mean of the same, pulled halfway to 1."""

    def __init__(self, tg):
        self.tg = {t: v for t, v in tg.items()}
        self.idx = {t: [(s, d) for d, s, _ in v] for t, v in tg.items()}
        self.cache = {}

    def blended(self, t, season, date):
        v, idx = self.tg.get(t, []), self.idx.get(t, [])
        lo, hi = bisect.bisect_left(idx, (season, "")), bisect.bisect_left(idx, (season, date))
        l0, l1 = bisect.bisect_left(idx, (season - 1, "")), bisect.bisect_left(idx, (season, ""))
        this, last = [x[2] for x in v[lo:hi]], [x[2] for x in v[l0:l1]]
        w = min(1.0, LAST_AS / len(last)) if last else 0.0
        n = len(this) + w * len(last)
        return (sum(this) + w * sum(last)) / n if n else None

    def factor(self, opp, season, date):
        key = (season, date)
        if key not in self.cache:
            vals = {t: self.blended(t, season, date) for t in self.tg}
            vals = {t: x for t, x in vals.items() if x is not None}
            self.cache[key] = (vals, sum(vals.values()) / len(vals) if vals else None)
        vals, lg = self.cache[key]
        x = vals.get(opp)
        return 1.0 if x is None or not lg else 1 + OPP_PULL * (x / lg - 1)


def nb_ll(y, mu, r):
    mu = np.maximum(mu, 1e-3)
    return gammaln(y + r) - gammaln(r) - gammaln(y + 1) + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu))


def nb_size(y, mu):
    grid = np.geomspace(0.3, 1000, 400)
    ll = [nb_ll(y, mu, r).sum() for r in grid]
    return float(grid[int(np.argmax(ll))])


def p_over(mu, line, r):
    """P(over) from a negative binomial with mean mu; a whole-number line is read given no push."""
    mu = max(mu, 1e-3)
    d = st.nbinom(r, r / (r + mu))
    if line == math.floor(line):
        return float(d.sf(line) / (1 - d.pmf(line)))
    return float(d.sf(math.floor(line)))


def logit(p):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def logistic(X, y):
    b = np.zeros(X.shape[1])
    for _ in range(100):
        p = 1 / (1 + np.exp(-X @ b))
        step = np.linalg.solve(X.T @ (X * (p * (1 - p))[:, None]) + 1e-9 * np.eye(len(b)), X.T @ (y - p))
        b += step
        if np.abs(step).max() < 1e-10:
            break
    return b


# ---- lines -------------------------------------------------------------------------------------------------------
def main_rungs(odds=ODDS):
    """{(event, folded player): (Eastern date, home, away, line, best over, best under, no-vig over, {book: (over,
    under)})} near puck drop."""
    o = sqlite3.connect(f"file:{odds}?immutable=1", uri=True)
    raw, meta = defaultdict(lambda: defaultdict(dict)), {}
    for ev, ct, home, away, book, pl, side, line, price in o.execute(
            "SELECT event_id, commence_time, home_team, away_team, book, player, side, line, price FROM props WHERE "
            "snap_kind = 'tip' AND market = 'player_shots_on_goal' AND book IN ('fanduel', 'draftkings') "
            "AND price IS NOT NULL AND line IS NOT NULL"):
        raw[(ev, fold(pl))][float(line)].setdefault(book, [None, None])[0 if side == "Over" or side == "over" else 1] = float(price)
        meta[ev] = (dt.datetime.fromisoformat(ct.replace("Z", "+00:00")).astimezone(ET).date().isoformat(), home, away)
    o.close()
    out = {}
    for k, lb in raw.items():
        best = None
        for line, bk in lb.items():
            two = {b: v for b, v in bk.items() if v[0] and v[1]}
            if two:
                gap = min(abs(v[0] - 2.0) for v in two.values())
                if best is None or gap < best[0] - 1e-9:
                    best = (gap, line, two)
        if best:
            _g, line, two = best
            pair = two.get("fanduel") or two.get("draftkings")
            out[k] = (*meta[k[0]], line, max(v[0] for v in two.values()), max(v[1] for v in two.values()),
                      (1 / pair[0]) / (1 / pair[0] + 1 / pair[1]), {b: tuple(v) for b, v in two.items()})
    return out


def match(rungs, games, recs, names):
    """[(rung, record)] and counts: event to game by Eastern date (±1 day) and teams, player by folded name in the game,
    else a unique last name + first initial."""
    by_day = defaultdict(list)
    for gid, (date, teams) in games.items():
        by_day[date].append((gid, set(teams)))
    roster = defaultdict(dict)
    for (gid, pid), (g, _f) in recs.items():
        roster[gid][pid] = fold(g["name"])
    ev_gid, out, n = {}, [], defaultdict(int)
    for (ev, pk), r in rungs.items():
        date, home, away = r[0], names.get(fold(r[1])), names.get(fold(r[2]))
        if ev not in ev_gid:
            ev_gid[ev] = None
            d0 = dt.date.fromisoformat(date)
            for dd in (0, -1, 1):
                hit = [gid for gid, t in by_day[(d0 + dt.timedelta(days=dd)).isoformat()] if {home, away} <= t]
                if hit:
                    ev_gid[ev] = hit[0]
                    break
        gid = ev_gid[ev]
        n["props"] += 1
        if gid is None:
            n["no game"] += 1
            continue
        ro = roster.get(gid, {})
        pid = [p for p, nm in ro.items() if nm == pk]
        if not pid and pk:
            last, ini = pk.split()[-1], pk[0]
            pid = [p for p, nm in ro.items() if nm and nm.split()[-1] == last and nm[0] == ini]
        if len(pid) != 1:
            n["no player"] += 1
            continue
        out.append((r, recs[(gid, pid[0])]))
    n["matched"] = len(out)
    return out, dict(n)


# ---- the tests ---------------------------------------------------------------------------------------------------
def boot(v):
    v = np.asarray(v, float)
    if len(v) < 20:
        roi = float(v.mean()) if len(v) else None
        return {"n": len(v), "roi": roi}, f"n {len(v):5d}" + (f"  ROI {roi:+.3f}" if len(v) else "")
    bs = np.sort([rng.choice(v, len(v)).mean() for _ in range(2000)])
    d = {"n": len(v), "hit": float(np.mean(v > 0)), "roi": float(v.mean()), "lo": float(bs[100]), "hi": float(bs[1900])}
    return d, f"n {len(v):5d}  hit {d['hit']:.1%}  ROI {d['roi']:+.3f} [{d['lo']:+.3f},{d['hi']:+.3f}]"


def ll(p, y):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def bets_of(props, key):
    out = []
    for b in props:
        p = b[key]
        eo, eu = p * b["over"] - 1, (1 - p) * b["under"] - 1
        if max(eo, eu) >= EV_MIN:
            side = "over" if eo >= eu else "under"
            won = b["act"] > b["line"] if side == "over" else b["act"] < b["line"]
            out.append(dict(b, side=side, u=(b[side] - 1) if won else -1.0))
    return out


def main():
    by_pid, games, tg, names = load()
    pri = priors(by_pid)
    recs = {}
    for gl in by_pid.values():
        for g, f in history(gl):
            if f is not None and g["season"] >= FIT:
                recs[(g["gid"], g["pid"])] = (g, f)
    fit = [(g, f) for g, f in recs.values() if g["season"] == FIT]
    beta = toi_fit(fit)
    opp = Opp(tg)
    for g, f in recs.values():
        mins = toi_proj(f, beta)
        att, ot, sog = rates(f, g["grp"], pri)
        of = opp.factor(g["opp"], g["season"], g["date"])
        f["proj"] = sum(mins[k] / 60 * att[k] for k in STR) * ot * of
        f["var"] = sum(mins[k] / 60 * sog[k] for k in STR) * of
        f["mins"], f["of"] = mins, of
    yf = np.array([g["shots"] for g, f in fit], float)
    r = nb_size(yf, np.array([f["proj"] for g, f in fit]))
    rv = nb_size(yf, np.array([f["var"] for g, f in fit]))
    res = {"priors": pri, "toi_beta": {k: [round(float(x), 4) for x in v] for k, v in beta.items()}, "nb_size": r,
           "nb_size_variant": rv, "player_games": {s: sum(g["season"] == s for g, f in recs.values()) for s in (FIT,) + TEST}}
    print(f"player-games with a projection: {res['player_games']}")
    print(f"priors (per hour): {json.dumps({k: {a: round(b, 3) for a, b in v.items()} for k, v in pri.items()})}")
    for k in STR:
        print(f"  minutes {k}: 1, last game, last 5, season mean = {np.round(beta[k], 3).tolist()}")
    print(f"  negative binomial size {r:.1f} (variant {rv:.1f})")
    print("  all player-games, MAE model / variant / average:")
    for s in (FIT,) + TEST:
        a = [(g["shots"], f["proj"], f["var"], f["avg"]) for g, f in recs.values() if g["season"] == s]
        a = np.array(a)
        print(f"    {s}: {np.abs(a[:, 0] - a[:, 1]).mean():.4f} / {np.abs(a[:, 0] - a[:, 2]).mean():.4f} / "
              f"{np.abs(a[:, 0] - a[:, 3]).mean():.4f}  (n {len(a)})")

    rungs = main_rungs()
    pairs, counts = match(rungs, games, recs, names)
    res["matching"] = counts
    print(f"\nmain-line props near puck drop: {counts}")
    props = []
    for (date, _h, _a, line, over, under, q, books), (g, f) in pairs:
        if g["shots"] == line:
            continue
        props.append({"season": g["season"], "po": g["po"], "grp": g["grp"], "line": line, "over": over, "under": under,
                      "q": q, "act": g["shots"], "y": float(g["shots"] > line), "proj": f["proj"], "var": f["var"],
                      "avg": f["avg"], "pm": p_over(f["proj"], line, r), "pv": p_over(f["var"], line, rv), "k": len(props), "gid": g["gid"], "books": books})
    tr = [b for b in props if b["season"] == FIT]
    X = lambda bs, k: np.column_stack([np.ones(len(bs)), logit([b[k] for b in bs]), logit([b["q"] for b in bs])])
    cal = logistic(X(tr, "pm"), np.array([b["y"] for b in tr]))
    calv = logistic(X(tr, "pv"), np.array([b["y"] for b in tr]))
    for b, pc, pv in zip(props, 1 / (1 + np.exp(-X(props, "pm") @ cal)), 1 / (1 + np.exp(-X(props, "pv") @ calv))):
        b["p"], b["p_var"] = float(pc), float(pv)
    res["calibration"] = cal.tolist()
    res["calibration_variant"] = calv.tolist()
    print(f"  calibration (1, model, book) = {np.round(cal, 3).tolist()}  variant {np.round(calv, 3).tolist()}")

    res["A"], res["B"], res["C"], res["info"] = {}, {}, {}, {}
    print("\n== A: MAE on graded main-line props, model / plain average / the line (variant)")
    a_pass = True
    for s in (FIT,) + TEST:
        bs = [b for b in props if b["season"] == s]
        act = np.array([b["act"] for b in bs])
        m, a, l_, v = (float(np.abs(act - np.array([b[k] for b in bs])).mean()) for k in ("proj", "avg", "line", "var"))
        res["A"][s] = {"n": len(bs), "model": m, "avg": a, "line": l_, "variant": v}
        print(f"  {s}{' (fit)' if s == FIT else ''}: n {len(bs)}  {m:.4f} / {a:.4f} / {l_:.4f}  ({v:.4f})")
        if s in TEST:
            a_pass &= m < a
    res["A"]["pass"] = a_pass

    print("\n== B: log loss, model / book (variant)")
    b_pass = True
    for s in (FIT,) + TEST:
        bs = [b for b in props if b["season"] == s]
        y = np.array([b["y"] for b in bs])
        m, bk, v = ll([b["p"] for b in bs], y), ll([b["q"] for b in bs], y), ll([b["p_var"] for b in bs], y)
        res["B"][s] = {"model": m, "book": bk, "variant": v}
        print(f"  {s}{' (fit)' if s == FIT else ''}: {m:.5f} / {bk:.5f}  ({v:.5f})")
        if s in TEST:
            b_pass &= m < bk
    res["B"]["pass"] = b_pass

    print("\n== C: bets at EV >= 5%")
    test = [b for b in props if b["season"] in TEST]
    bets = bets_of(test, "p")
    per = {}
    for s in TEST:
        d, txt = boot([b["u"] for b in bets if b["season"] == s])
        per[s] = d
        print(f"  {s}: {txt}")
    pooled, txt = boot([b["u"] for b in bets])
    print(f"  pooled: {txt}")
    c_pass = bool(pooled.get("roi", -1) > 0 and pooled.get("lo", -1) > 0 and all(per[s].get("roi", -1) > 0 for s in TEST))
    res["C"] = {"seasons": per, "pooled": pooled, "pass": c_pass}
    print("  by side, line, group and part of season (pooled):")
    lb = lambda x: "3.5+" if x >= 3.5 else f"{x:.1f}"
    for name, key in (("side", lambda b: b["side"]), ("line", lambda b: lb(b["line"])), ("group", lambda b: b["grp"]),
                      ("part", lambda b: "playoffs" if b["po"] else "regular")):
        for val in sorted({key(b) for b in bets}):
            d, txt = boot([b["u"] for b in bets if key(b) == val])
            res["info"][f"C {name} {val}"] = d
            print(f"    {name} {val:9s} {txt}")
    vb = bets_of(test, "p_var")
    d, txt = boot([b["u"] for b in vb])
    res["info"]["C variant"] = d
    print(f"  variant (plain SOG rate): {txt}")

    print("\n== D: the NBA under rule on SOG (plain average 30-50% below the line, under -150 or better)")
    ping = [b for b in props if b["line"] and RATIO_AT > b["avg"] / b["line"] and PING_LO <= b["avg"] / b["line"] < PING_HI
            and b["under"] >= PRICE_MIN - 1e-9]
    for b in ping:
        b["u_d"] = (b["under"] - 1) if b["act"] < b["line"] else -1.0
    dper = {}
    for s in (FIT,) + TEST:
        d, txt = boot([b["u_d"] for b in ping if b["season"] == s])
        dper[s] = d
        print(f"  {s}: {txt}")
    dp, txt = boot([b["u_d"] for b in ping])
    print(f"  pooled: {txt}")
    pos = sum(dper[s].get("roi", -1) > 0 for s in dper)
    d_hold = bool(dp.get("roi", -1) > 0 and dp.get("lo", -1) > 0 and pos >= 2)
    res["D"] = {"seasons": dper, "pooled": dp, "seasons_positive": pos, "holds": d_hold}

    print("\n== information (after the result): the book alone, recalibrated on 2023-24 (logit P = b0 + b1 logit(book))")
    Xb = lambda bs: np.column_stack([np.ones(len(bs)), logit([b["q"] for b in bs])])
    calb = logistic(Xb(tr), np.array([b["y"] for b in tr]))
    for b, pb in zip(props, 1 / (1 + np.exp(-Xb(props) @ calb))):
        b["p_book"] = float(pb)
    res["info"]["calibration_book"] = calb.tolist()
    print(f"  calibration (1, book) = {np.round(calb, 3).tolist()}")
    for s in TEST:
        bs = [b for b in props if b["season"] == s]
        y = np.array([b["y"] for b in bs])
        print(f"  {s} log loss, book recalibrated {ll([b['p_book'] for b in bs], y):.5f}  (model {res['B'][s]['model']:.5f})")
    bb = bets_of(test, "p_book")
    d, txt = boot([b["u"] for b in bb])
    res["info"]["C book alone"] = d
    print(f"  bets, book alone: {txt}")
    kb = {b["k"] for b in bb}
    for name, sel in (("model bets the book alone also makes", [b for b in bets if b["k"] in kb]),
                      ("model bets the book alone doesn't", [b for b in bets if b["k"] not in kb])):
        d, txt = boot([b["u"] for b in sel])
        res["info"][f"C {name}"] = d
        print(f"  {name}: {txt}")
    for s in TEST:
        d, txt = boot([b["u"] for b in bb if b["season"] == s])
        print(f"    book alone {s}: {txt}")

    print("\n== information (after the result): one book's prices, and games as clusters")
    for bk in ("fanduel", "draftkings"):
        one = [dict(b, over=b["books"][bk][0], under=b["books"][bk][1]) for b in test if bk in b["books"]]
        ob = bets_of(one, "p")
        for s in TEST:
            d, txt = boot([b["u"] for b in ob if b["season"] == s])
            print(f"  {bk} {s}: {txt}")
        d, txt = boot([b["u"] for b in ob])
        res["info"][f"C {bk} only"] = d
        print(f"  {bk} pooled: {txt}")
    by_g = defaultdict(list)
    for b in bets:
        by_g[b["gid"]].append(b["u"])
    gs = list(by_g.values())
    cl = np.sort([np.concatenate([gs[i] for i in rng.integers(0, len(gs), len(gs))]).mean() for _ in range(2000)])
    res["info"]["C pooled, games as clusters"] = (float(cl[100]), float(cl[1900]), len(gs))
    print(f"  C pooled, resampling games ({len(gs)}): 90% [{cl[100]:+.3f},{cl[1900]:+.3f}]")

    print("\n== information: the book's no-vig over against the actual over rate")
    for s in (FIT,) + TEST:
        bs = [b for b in props if b["season"] == s]
        res["info"][f"book {s}"] = (float(np.mean([b["q"] for b in bs])), float(np.mean([b["y"] for b in bs])))
        print(f"  {s}: no-vig over {res['info'][f'book {s}'][0]:.4f}  actual over {res['info'][f'book {s}'][1]:.4f}")

    print(f"\nA {'PASS' if a_pass else 'FAIL'}, B {'PASS' if b_pass else 'FAIL'}, C {'PASS' if c_pass else 'FAIL'}, "
          f"D {'HOLDS' if d_hold else 'DOES NOT HOLD'}")
    OUT.write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pull", action="store_true")
    a = ap.parse_args()
    sys.exit(pull() if a.pull else main())
