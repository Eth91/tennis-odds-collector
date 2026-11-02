"""NBA_REBMATCH_PREREG.md: a rebounding matchup from where the misses come from and how far out a player grabs his
rebounds. Research only: nothing is bet.

    python3 nba_rebmatch.py --fetch            # last-season rebound profiles (stats.nba.com playerdashptreb), resumable
    python3 nba_rebmatch.py --run [--json OUT] # the registered tests
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
GAMELOGS = HERE / ".projdata" / "nba_gamelogs.sqlite"
REBDIST = HERE / ".projdata" / "rebdist_hist.sqlite"
SHOTS = HERE / ".projdata" / "shots_hist.sqlite"
ODDS = Path.home() / "nba-engine" / "basketball_nba_odds_hist.sqlite"
SEASONS = ("2023-24", "2024-25")
MISS_BANDS = ("0-6 Feet", "7-13 Feet", "13-19 Feet", "19+ Feet")        # stats.nba.com's miss-distance bands
NEAR_BANDS, GRAB_BANDS = ("0-3 Feet", "3-6 Feet"), ("0-3 Feet", "3-6 Feet", "6-10 Feet", "10+ Feet")
OPEN_BAND = "0 Contesting Rebounders"
K_TEAM, MIN_GAMES, MIN_MPG = 10.0, 5, 20.0
NEAR_AT, FAR_AT = 0.75, 0.35
EV_AT, MIN_PICK, LAMBDAS = 0.03, 150, (0.01, 0.1, 1.0, 10.0, 100.0)
FEATURES = ("logit_book", "reb_r", "M", "near", "open", "f_short", "f_long", "f_own", "mpg")
PREV = {"2023-24": "2022-23", "2024-25": "2023-24"}
MIN_PREV_GAMES = 20
URL = ("https://stats.nba.com/stats/playerdashptreb?PlayerID={pid}&TeamID=0&Season={season}&SeasonType=Regular%20Season"
       "&PerMode=Totals&LeagueID=00&LastNGames=0&Month=0&OpponentTeamID=0&Period=0&DateFrom=&DateTo=&GameSegment="
       "&Location=&Outcome=&SeasonSegment=&VsConference=&VsDivision=")
DDL = """CREATE TABLE IF NOT EXISTS rebdist (season TEXT, pid INTEGER, kind TEXT, band TEXT, reb REAL, oreb REAL, dreb REAL,
    PRIMARY KEY (season, pid, kind, band));
CREATE TABLE IF NOT EXISTS done (season TEXT, pid INTEGER, rows INTEGER, PRIMARY KEY (season, pid));"""
KINDS = {"OverallRebounding": "overall", "ShotTypeRebounding": "shot_type", "NumContestedRebounding": "contested",
         "ShotDistanceRebounding": "miss_dist", "RebDistanceRebounding": "grab_dist"}


def _get(url, tries=4):
    """All result sets of a stats.nba.com call, with nba_tracking's headers and back-off."""
    from curl_cffi import requests as cr
    import nba_tracking as T
    for k in range(tries):
        try:
            r = cr.get(url, impersonate="chrome", timeout=60, headers=T.H)
            if r.status_code == 200:
                return r.json()["resultSets"]
            err = f"HTTP {r.status_code}"
        except Exception as e:                       # timeouts, resets
            err = type(e).__name__
        time.sleep(5 * (k + 1))
    raise RuntimeError(f"gave up after {tries} tries ({err})")


def players(gamelogs=GAMELOGS):
    """(previous season, pid) for everyone with >= 20 games in a previous season who played in the test season after it."""
    g = sqlite3.connect(f"file:{gamelogs}?mode=ro", uri=True)
    out = []
    for season, prev in PREV.items():
        now = {p for (p,) in g.execute("SELECT DISTINCT player_id FROM logs_full WHERE season = ? AND min > 0", (season,))}
        out += [(prev, p) for (p,) in g.execute("SELECT player_id FROM logs_full WHERE season = ? AND min > 0 GROUP BY player_id "
                                                 "HAVING COUNT(*) >= ?", (prev, MIN_PREV_GAMES)) if p in now]
    return sorted(set(out))


def fetch(db=REBDIST, gamelogs=GAMELOGS, get=None, pause=1.0, workers=3):
    """Every (season, player) not fetched yet, `workers` calls at a time, each worker pausing between its calls. An empty
    answer is stored as done with 0 rows (he has no tracking)."""
    from concurrent.futures import ThreadPoolExecutor
    get = get or _get
    con = sqlite3.connect(db)
    con.executescript(DDL)
    have = {(s, p) for s, p in con.execute("SELECT season, pid FROM done")}
    todo = [sp for sp in players(gamelogs) if sp not in have]
    print(f"{len(todo)} players to fetch", flush=True)

    def one(sp):
        time.sleep(pause)
        try:
            return get(URL.format(pid=sp[1], season=sp[0]))
        except RuntimeError as e:                    # gave up after retries: not marked done, so the next run retries
            print(f"  {sp}: {e}", flush=True)
            return None
    with ThreadPoolExecutor(workers) as ex:
        for i, ((season, pid), sets) in enumerate(zip(todo, ex.map(one, todo)), 1):
            if sets is None:
                continue
            n = 0
            for rs in sets:
                kind = KINDS.get(rs["name"])
                if not kind:
                    continue
                h = rs["headers"]
                ix = {c: k for k, c in enumerate(h)}
                lab = next((c for c in h if c.endswith("_RANGE")), "OVERALL")
                for r in rs["rowSet"]:
                    con.execute("INSERT OR REPLACE INTO rebdist VALUES (?,?,?,?,?,?,?)",
                                (season, pid, kind, r[ix[lab]] if lab in ix else "Overall", r[ix["REB"]], r[ix["OREB"]], r[ix["DREB"]]))
                    n += 1
            con.execute("INSERT OR REPLACE INTO done VALUES (?,?,?)", (season, pid, n))
            con.commit()
            if i % 50 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}", flush=True)
    con.close()


def band(x, y):
    """The miss-distance band (index into MISS_BANDS) of a shot at (x, y), tenths of a foot from the basket."""
    d = math.hypot(x, y) / 10
    return 0 if d < 7 else 1 if d < 13 else 2 if d < 19 else 3


def profiles(db=REBDIST, gamelogs=GAMELOGS):
    """{(previous season, pid): {dreb: [4], oreb: [4] per game, near, open}} from last season's tracking."""
    g = sqlite3.connect(f"file:{gamelogs}?mode=ro", uri=True)
    games = {(s, p): n for s, p, n in g.execute("SELECT season, player_id, COUNT(*) FROM logs_full WHERE min > 0 GROUP BY season, player_id")}
    r = defaultdict(dict)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for season, pid, kind, bd, reb, oreb, dreb in con.execute("SELECT season, pid, kind, band, reb, oreb, dreb FROM rebdist"):
        r[(season, pid)][(kind, bd)] = (reb or 0.0, oreb or 0.0, dreb or 0.0)
    out = {}
    for key, rows in r.items():
        n = games.get(key, 0)
        grab = sum(rows.get(("grab_dist", b), (0, 0, 0))[0] for b in GRAB_BANDS)
        cont = sum(v[0] for (k, _b), v in rows.items() if k == "contested")
        miss = [rows.get(("miss_dist", b), (0, 0, 0)) for b in MISS_BANDS]
        if n < MIN_PREV_GAMES or not grab or not cont or not sum(m[0] for m in miss):
            continue
        out[key] = {"dreb": [m[2] / n for m in miss], "oreb": [m[1] / n for m in miss],
                    "near": sum(rows.get(("grab_dist", b), (0, 0, 0))[0] for b in NEAR_BANDS) / grab,
                    "open": rows.get(("contested", OPEN_BAND), (0, 0, 0))[0] / cont}
    return out


def props(odds_db=ODDS, name2pid=None):
    """{(date, pid): (line, best over, best under, no-vig over)} for rebounds at the tip line: the FanDuel/DraftKings main
    closest to even; the no-vig over from FanDuel's pair, else DraftKings'."""
    import nba_margin_refit as MR
    o = sqlite3.connect(f"file:{odds_db}?mode=ro", uri=True)
    raw = defaultdict(lambda: defaultdict(dict))
    for d, pl, line, side, price, book in o.execute("SELECT game_date, player, line, side, price, book FROM props WHERE "
                                                    "market = 'player_rebounds' AND price IS NOT NULL AND line IS NOT NULL"):
        if book in ("fanduel", "draftkings"):
            raw[(d, name2pid.get(MR.norm(pl)))][float(line)].setdefault(book, [None, None])[0 if side == "over" else 1] = float(price)
    out = {}
    for k, lb in raw.items():
        best = None
        for line, bk in lb.items():
            two = {b: v for b, v in bk.items() if v[0] and v[1]}
            if two:
                gap = min(abs(v[0] - 2.0) for v in two.values())
                if best is None or gap < best[0]:
                    best = (gap, line, two)
        if best and k[1] is not None:
            _g, line, two = best
            pair = two.get("fanduel") or two.get("draftkings")
            out[k] = (line, max(v[0] for v in two.values()), max(v[1] for v in two.values()),
                      (1 / pair[0]) / (1 / pair[0] + 1 / pair[1]))
    return out


class Misses:
    """Each team's own missed FGA per game by band, season to date: add() a date's games after reading the date."""

    def __init__(self):
        self.n, self.m, self.lg_n, self.lg_m = defaultdict(int), defaultdict(lambda: [0.0] * 4), 0, [0.0] * 4

    def factor(self, team, b=None):
        """The team's misses per game in band b (all bands if None), shrunk k = 10 toward the league, over the league's."""
        if not self.lg_n:
            return 1.0
        bs = range(4) if b is None else (b,)
        lg = sum(self.lg_m[i] for i in bs) / self.lg_n
        if not lg:
            return 1.0
        mine = sum(self.m[team][i] for i in bs)
        return (mine + K_TEAM * lg) / (self.n[team] + K_TEAM) / lg

    def third(self, teams, b, team):
        """'top' when at least 2/3 of these teams are strictly below `team` in band b, 'bottom' when 2/3 are strictly
        above it, else None (ties never put a team in a third)."""
        me, v = self.factor(team, b), [self.factor(t, b) for t in teams]
        if len(v) < 3:
            return None
        return "top" if sum(x < me for x in v) >= 2 * len(v) / 3 else "bottom" if sum(x > me for x in v) >= 2 * len(v) / 3 else None

    def add(self, team, bands):
        self.n[team] += 1
        self.lg_n += 1
        for i, c in enumerate(bands):
            self.m[team][i] += c
            self.lg_m[i] += c


def build(gamelogs=GAMELOGS, shots_db=SHOTS, odds_db=ODDS, rebdist=REBDIST):
    """One row per rebounds prop with features from games before its date and last season's profile."""
    import nba_margin_refit as MR
    g = sqlite3.connect(f"file:{gamelogs}?mode=ro", uri=True)
    name2pid = {MR.norm(nm): pid for pid, nm in g.execute("SELECT DISTINCT player_id, player FROM logs_full")}
    lines, prof = props(odds_db, name2pid), profiles(rebdist, gamelogs)
    s = sqlite3.connect(f"file:{shots_db}?mode=ro", uri=True)
    rows = []
    for season in SEASONS:
        team_of, teams_of, by_date = {}, defaultdict(set), defaultdict(list)
        for d, gid, team, pid, mn, reb in g.execute("SELECT date, game_id, team, player_id, min, reb FROM logs_full WHERE season = ?", (season,)):
            team_of[(gid, pid)] = team
            teams_of[gid].add(team)
            if mn:
                by_date[d].append((gid, team, pid, mn, reb or 0))
        miss = defaultdict(lambda: [0] * 4)                      # (gid, team) -> its missed FGA by band
        for gid, pid, x, y in s.execute("SELECT gid, pid, x, y FROM shots WHERE season = ? AND made = 0", (season,)):
            t = team_of.get((gid, pid))
            if t is not None:
                miss[(gid, t)][band(x, y)] += 1
        M, box = Misses(), defaultdict(lambda: [0, 0.0, 0.0])    # pid -> [games, minutes, rebounds]
        for d in sorted(by_date):
            played = list(M.n)
            for gid, team, pid, _mn, reb in by_date[d]:
                key = (d, pid)
                n, mins, rebs = box[pid]
                pr = prof.get((PREV[season], pid))
                if key not in lines or n < MIN_GAMES or pr is None:
                    continue
                opp = next((t for t in teams_of[gid] if t != team), None)
                if opp is None:
                    continue
                line, over, under, q = lines[key]
                f_opp = [M.factor(opp, b) for b in range(4)]
                f_own = [M.factor(team, b) for b in range(4)]
                base = sum(pr["dreb"]) + sum(pr["oreb"])
                m_fac = (sum(a * f for a, f in zip(pr["dreb"], f_opp)) + sum(a * f for a, f in zip(pr["oreb"], f_own))) / base
                reb_pg = rebs / n
                th_s, th_l = M.third(played, 0, opp), M.third(played, 3, opp)
                rows.append({"season": season, "date": d, "pid": pid, "line": line, "over": over, "under": under, "q": q,
                             "actual": reb, "mpg": mins / n, "reb_r": reb_pg / line, "xreb_r": reb_pg * m_fac / line,
                             "xreb0_r": reb_pg / line, "M": m_fac, "near": pr["near"], "open": pr["open"],
                             "f_short": f_opp[0], "f_long": f_opp[3], "f_own": M.factor(team),
                             "opp_short_top": th_s == "top", "opp_short_bottom": th_s == "bottom",
                             "opp_long_top": th_l == "top", "opp_long_bottom": th_l == "bottom",
                             "u": 0.0 if reb == line else (over - 1 if reb > line else -1.0),
                             "u_under": 0.0 if reb == line else (under - 1 if reb < line else -1.0),
                             "logit_book": math.log(q / (1 - q))})
            for gid in {x[0] for x in by_date[d]}:                # the date's games join the season-to-date state
                for t in teams_of[gid]:
                    M.add(t, miss[(gid, t)])
            for _gid, _team, pid, mn, reb in by_date[d]:
                b = box[pid]
                b[0] += 1
                b[1] += mn
                b[2] += reb
    return rows


def summ(rs, key="u"):
    """Bets, hit rate (pushes out) and ROI, on the profit column `key` (u: the over, u_under: the under)."""
    if not rs:
        return {"n": 0}
    np_ = [r for r in rs if r["actual"] != r["line"]]
    return {"n": len(rs), "hit": round(float(np.mean([r[key] > 0 for r in np_])), 4) if np_ else None,
            "roi": round(float(np.mean([r[key] for r in rs])), 4)}


def rules_b(rows):
    """The user's logic at fixed thresholds: each cell, and its baseline, by season."""
    base = [r for r in rows if r["mpg"] >= MIN_MPG]
    cells = {"B1 rim rebounder vs short misses: over": (lambda r: r["near"] >= NEAR_AT and r["opp_short_top"], "u"),
             "B2 long rebounder vs long misses: over": (lambda r: 1 - r["near"] >= FAR_AT and r["opp_long_top"], "u"),
             "B3 rim rebounder vs few short misses: under": (lambda r: r["near"] >= NEAR_AT and r["opp_short_bottom"], "u_under"),
             "B4 long rebounder vs few long misses: under": (lambda r: 1 - r["near"] >= FAR_AT and r["opp_long_bottom"], "u_under")}
    out = {"baseline": {s: {"overs": summ([r for r in base if r["season"] == s]),
                            "unders": summ([r for r in base if r["season"] == s], "u_under")} for s in SEASONS}}
    for name, (pick, key) in cells.items():
        res = {s: summ([r for r in base if r["season"] == s and pick(r)], key) for s in SEASONS}
        side = "overs" if key == "u" else "unders"
        res["passes"] = all(res[s].get("n") and res[s]["roi"] > 0 and res[s]["roi"] > out["baseline"][s][side]["roi"] for s in SEASONS)
        out[name] = res
    return out


def solver_c(rows):
    """L2 logistic for P(over) beyond the book, fit on one season, bet either side on the other (as nba_pts solver B)."""
    import nba_pts as PTS
    base = [r for r in rows if r["mpg"] >= MIN_MPG]
    out = {"features": list(FEATURES), "directions": {}}

    def design(rs, mu=None, sd=None):
        F = np.array([[r[f] for f in FEATURES] for r in rs], float)
        if mu is None:
            mu, sd = F.mean(0), F.std(0)
            sd[sd == 0] = 1.0
        return np.hstack([np.ones((len(rs), 1)), (F - mu) / sd]), mu, sd
    for fit, chk in ((SEASONS[0], SEASONS[1]), (SEASONS[1], SEASONS[0])):
        fr = sorted([r for r in base if r["season"] == fit and r["actual"] != r["line"]], key=lambda r: r["date"])
        X, mu, sd = design(fr)
        y = np.array([r["actual"] > r["line"] for r in fr], float)
        folds = np.array_split(np.arange(len(fr)), 5)                # contiguous date blocks
        cv = {}
        for lam in LAMBDAS:
            ll = []
            for f in folds:
                tr = np.setdiff1d(np.arange(len(fr)), f)
                ll.append(PTS.logloss(1 / (1 + np.exp(-X[f] @ PTS.logistic(X[tr], y[tr], lam))), y[f]))
            cv[lam] = float(np.mean(ll))
        lam = min(cv, key=cv.get)
        w = PTS.logistic(X, y, lam)
        cr = [r for r in base if r["season"] == chk]
        Xc, _m, _s = design(cr, mu, sd)
        p = 1 / (1 + np.exp(-Xc @ w))
        np_ = np.array([r["actual"] != r["line"] for r in cr])
        yc = np.array([r["actual"] > r["line"] for r in cr], float)
        overs = [dict(r, pl=r["u"]) for r, pp in zip(cr, p) if pp * r["over"] - 1 >= EV_AT]
        unders = [dict(r, pl=r["u_under"]) for r, pp in zip(cr, p) if (1 - pp) * r["under"] - 1 >= EV_AT and pp * r["over"] - 1 < EV_AT]
        out["directions"][f"fit {fit} -> test {chk}"] = {
            "lambda": lam, "coefficients (per SD)": {f: round(float(c), 4) for f, c in zip(("intercept",) + FEATURES, w)},
            "test_logloss": {"model": round(PTS.logloss(p[np_], yc[np_]), 5),
                             "book": round(PTS.logloss(np.array([r["q"] for r in cr])[np_], yc[np_]), 5)},
            "test_bets": summ(overs + unders, "pl"), "overs": summ(overs, "pl"), "unders": summ(unders, "pl")}
    d = list(out["directions"].values())
    out["passes"] = all(x["test_bets"].get("n", 0) >= MIN_PICK and x["test_bets"]["roi"] > 0
                        and x["test_logloss"]["model"] < x["test_logloss"]["book"] for x in d)
    return out


def run(rows):
    import nba_pts as PTS
    return {"rows": len(rows), "by_season": {s: sum(r["season"] == s for r in rows) for s in SEASONS},
            "A xREB (matchup)": PTS.solver_a(rows, "xreb_r"), "A xREB0 (no matchup)": PTS.solver_a(rows, "xreb0_r"),
            "B": rules_b(rows), "C": solver_c(rows)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()
    if a.fetch:
        fetch()
    if a.run:
        res = run(build())
        print(json.dumps(res, indent=1))
        if a.json:
            Path(a.json).write_text(json.dumps(res, indent=1))
