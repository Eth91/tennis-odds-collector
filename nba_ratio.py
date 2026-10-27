#!/usr/bin/env python3
"""The user's volume-to-line ratios (NBA_RATIO_PREREG.md), backtested at the archive's tip lines.

  FGA  over in points   when season-to-date FGA per game            >= the points line
  PA   over in assists  when season-to-date potential assists/game  >= 2 x the assists line
  RC   over in rebounds when season-to-date rebound chances/game    >= 2 x the rebounds line (2.5x also reported)
Season to date = his games this season before the date (minutes > 0), at least 3. No hindsight: all known pre-game.

    python3 nba_ratio.py --gamelogs .projdata/nba_gamelogs.sqlite --odds ~/nba-engine/basketball_nba_odds_hist.sqlite \
        --tracking .projdata/tracking_hist.sqlite [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

import nba_margin_refit as MR

SEASONS = ("2023-24", "2024-25")
MIN_GAMES, EARLY = 3, 10
FDK = ("fanduel", "draftkings")
MARKETS = {"player_points": "points", "player_assists": "assists", "player_rebounds": "rebounds"}
RULES = {"FGA": ("points", "fga", 1.0), "PA": ("assists", "pa", 2.0), "RC": ("rebounds", "rc", 2.0), "RC2.5": ("rebounds", "rc", 2.5)}
BANDS = {"FGA": (1.1, 1.25), "PA": (2.25, 2.5), "RC": (2.25, 2.5), "RC2.5": (2.75, 3.0)}
ACTUAL = {"points": "pts", "assists": "ast", "rebounds": "reb"}


def main_line(lb):
    """(line, best FanDuel/DraftKings over) at the two-sided rung whose over is nearest even money."""
    best = None
    for line, bk in lb.items():
        ov = [v[0] for b, v in bk.items() if b in FDK and v[0] and v[1]]
        if ov:
            gap = min(abs(x - 2.0) for x in ov)
            if best is None or gap < best[0] - 1e-9:
                best = (gap, line, max(ov))
    return (best[1], best[2]) if best else None


def build(gamelogs_db, odds_db, tracking_db=None):
    g = sqlite3.connect(f"file:{gamelogs_db}?mode=ro", uri=True)
    name2pid = {MR.norm(nm): pid for pid, nm in g.execute("SELECT DISTINCT player_id, player FROM logs_full")}
    groups = {pid: (pos or "")[:1] or None for pid, pos in g.execute("SELECT player_id, position FROM positions")}
    trk = {}
    if tracking_db and Path(tracking_db).exists():
        t = sqlite3.connect(f"file:{tracking_db}?mode=ro", uri=True)
        trk = {(d, p): (pa or 0.0, rc or 0.0) for d, p, pa, rc in t.execute("SELECT date, player_id, potential_ast, reb_chances FROM tracking")}
        tracked_dates = {d for (d, _m) in t.execute("SELECT date, measure FROM fetched")}
    o = sqlite3.connect(f"file:{odds_db}?mode=ro", uri=True)
    raw = defaultdict(lambda: defaultdict(dict))
    for d, pl, m, line, side, price, book in o.execute(
            "SELECT game_date, player, market, line, side, price, book FROM props WHERE market IN ('player_points', "
            "'player_assists', 'player_rebounds') AND price IS NOT NULL AND line IS NOT NULL"):
        if book in FDK:
            raw[(d, name2pid.get(MR.norm(pl)), MARKETS[m])][float(line)].setdefault(book, [None, None])[0 if side == "over" else 1] = float(price)
    rows = []
    for s in SEASONS:
        by_date = defaultdict(list)
        teams_of = defaultdict(set)                       # game -> its two teams
        for d, pid, mn, fga, pts, ast, reb, gid, team in g.execute(
                "SELECT date, player_id, min, fga, pts, ast, reb, game_id, team FROM logs_full WHERE season = ?", (s,)):
            teams_of[gid].add(team)
            if mn:
                by_date[d].append((pid, fga or 0, pts or 0, ast or 0, reb or 0, mn, gid, team))
        allowed = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))   # opponent -> group -> [points, rebounds] allowed
        tgames, league, league_tg = defaultdict(int), defaultdict(lambda: [0.0, 0.0]), 0
        acc = defaultdict(lambda: {"n": 0, "min": 0.0, "fga": 0.0, "pa": 0.0, "rc": 0.0, "n_trk": 0})
        for d in sorted(by_date):
            for pid, fga, pts, ast, reb, _mn, gid, team in by_date[d]:
                a = acc[pid]
                opp = next((t for t in teams_of[gid] if t != team), None)
                grp = groups.get(pid)
                dvp = None                                    # amendment 4: defense vs position, before the date
                if opp and grp and tgames[opp] >= 10 and league_tg and league[grp][0]:
                    al = allowed[opp][grp]
                    dvp = ((al[0] / tgames[opp]) / (league[grp][0] / league_tg), (al[1] / tgames[opp]) / (league[grp][1] / league_tg))
                if a["n"] >= MIN_GAMES:
                    for mk in ("points", "assists", "rebounds"):
                        lb = raw.get((d, pid, mk))
                        ml = main_line(lb) if lb else None
                        if not ml:
                            continue
                        line, price = ml
                        act = {"points": pts, "assists": ast, "rebounds": reb}[mk]
                        rows.append({"season": s, "date": d, "pid": pid, "market": mk, "line": line, "price": price,
                                     "games": a["n"], "mpg": a["min"] / a["n"], "fga": a["fga"] / a["n"],
                                     "pa": a["pa"] / a["n_trk"] if a["n_trk"] else None,
                                     "rc": a["rc"] / a["n_trk"] if a["n_trk"] else None, "actual": act,
                                     "dvp_pts": dvp[0] if dvp else None, "dvp_reb": dvp[1] if dvp else None,
                                     "u": (price - 1) if act > line else 0.0 if act == line else -1.0})
            for gid in {r[6] for r in by_date[d]}:            # amendment 4: the date's games join the allowances
                for t in teams_of[gid]:
                    tgames[t] += 1
                    league_tg += 1
            for pid, fga, pts, ast, reb, mn, gid, team in by_date[d]:
                opp = next((t for t in teams_of[gid] if t != team), None)
                grp = groups.get(pid)
                if opp and grp:
                    allowed[opp][grp][0] += pts
                    allowed[opp][grp][1] += reb
                    league[grp][0] += pts
                    league[grp][1] += reb
            for pid, fga, pts, ast, reb, mn, _gid, _team in by_date[d]:      # the date's games join the season-to-date totals
                a = acc[pid]
                a["n"] += 1
                a["min"] += mn
                a["fga"] += fga
                if trk and d in tracked_dates:                    # a missing row on a fetched date is 0 (the feeds omit zeros)
                    pa, rc = trk.get((d, pid), (0.0, 0.0))
                    a["pa"] += pa
                    a["rc"] += rc
                    a["n_trk"] += 1
    return rows


def summ(rs):
    if not rs:
        return {"n": 0}
    np_ = [r for r in rs if r["actual"] != r["line"]]
    return {"n": len(rs), "hit": round(float(np.mean([r["actual"] > r["line"] for r in np_])), 4) if np_ else None,
            "roi": round(float(np.mean([r["u"] for r in rs])), 4)}


def report(rows):
    res = {}
    for rule, (mk, key, k) in RULES.items():
        out = {}
        for s in SEASONS:
            base = [r for r in rows if r["season"] == s and r["market"] == mk and r[key] is not None]
            hit = [r for r in base if r[key] >= k * r["line"]]
            lo, hi = BANDS[rule]
            band = lambda r: "low" if r[key] < lo * r["line"] else "high" if r[key] >= hi * r["line"] else "mid"
            out[s] = {"rule": summ(hit), "all_overs": summ(base), "share_of_props": round(len(hit) / len(base), 4) if base else None,
                      "bands": {b: summ([r for r in hit if band(r) == b]) for b in ("low", "mid", "high")},
                      "early (<= 10 games)": summ([r for r in hit if r["games"] <= EARLY]),
                      "later": summ([r for r in hit if r["games"] > EARLY])}
        out["passes"] = all(out[s]["rule"].get("n") and out[s]["rule"]["roi"] > 0 and out[s]["rule"]["roi"] > out[s]["all_overs"]["roi"]
                            for s in SEASONS)
        res[rule] = out
    return res


# ── amendment 1: the solver ───────────────────────────────────────────────────────────────────────────────────
GRID = {"FGA": [round(0.80 + 0.05 * i, 2) for i in range(25)], "PA": [round(1.0 + 0.1 * i, 1) for i in range(31)],
        "RC": [round(1.0 + 0.1 * i, 1) for i in range(31)]}
MIN_PICK = 150


def solve(rows, rule):
    """ROI by threshold in each season; the best k (n >= MIN_PICK) on one season, checked on the other, both ways."""
    mk, key, _k = RULES[rule]
    curve = {}
    for k in GRID[rule]:
        curve[k] = {s: summ([r for r in rows if r["season"] == s and r["market"] == mk and r[key] is not None
                             and r[key] >= k * r["line"]]) for s in SEASONS}
    out = {"curve": {str(k): v for k, v in curve.items()}, "checks": {}}
    for fit, chk in ((SEASONS[0], SEASONS[1]), (SEASONS[1], SEASONS[0])):
        ok = [k for k in GRID[rule] if curve[k][fit].get("n", 0) >= MIN_PICK]
        if not ok:
            out["checks"][f"pick on {fit}"] = None
            continue
        k = max(ok, key=lambda x: curve[x][fit]["roi"])
        i = GRID[rule].index(k)
        nb = [GRID[rule][j] for j in (i - 1, i + 1) if 0 <= j < len(GRID[rule])]
        out["checks"][f"pick on {fit}"] = {"k": k, "fit": curve[k][fit], "check": curve[k][chk],
                                           "neighbours": {str(x): curve[x] for x in nb}}
    picks = [v for v in out["checks"].values() if v]
    out["profitable"] = bool(picks) and all(
        v["check"].get("n") and v["check"]["roi"] > 0 and all(n_[s]["roi"] > 0 for n_ in v["neighbours"].values() for s in SEASONS if n_[s].get("n"))
        for v in picks)
    return out


# ── amendment 2: minutes first ────────────────────────────────────────────────────────────────────────────────
MIN_MPG = 20.0


def minutes_first(rows):
    """Each rule at 20+ season minutes (FGA at k = 1.0, 1.1, 1.2), its baseline, and the solver within 20+ minutes."""
    r20 = [r for r in rows if r["mpg"] >= MIN_MPG]
    res = {}
    for rule, ks in (("FGA", (1.0, 1.1, 1.2)), ("PA", (2.0,)), ("RC", (2.0, 2.5))):
        mk, key, _k = RULES[rule]
        out = {}
        for s in SEASONS:
            base = [r for r in r20 if r["season"] == s and r["market"] == mk and r[key] is not None]
            out[s] = {"all_overs_20min": summ(base),
                      **{f"k={k}": summ([r for r in base if r[key] >= k * r["line"]]) for k in ks}}
        prim = f"k={ks[0]}"
        out["passes"] = all(out[s][prim].get("n") and out[s][prim]["roi"] > 0 and out[s][prim]["roi"] > out[s]["all_overs_20min"]["roi"]
                            for s in SEASONS)
        out["solver"] = solve(r20, rule)
        res[rule] = out
    return res


# ── amendment 4: matchup conditions ───────────────────────────────────────────────────────────────────────────
def matchup_test(rows, zone_rows):
    """PTS_MATCH and REB_MATCH against their ratio rules; each condition alone; top-tercile versions."""
    zone = {(z["date"], z["pid"]): z["zone"] for z in zone_rows}
    for r in rows:
        r["zone"] = zone.get((r["date"], r["pid"])) if r["market"] == "points" else None
    fit = [r for r in rows if r["season"] == SEASONS[0]]
    q = lambda key, mk, pct: float(np.percentile([r[key] for r in fit if r["market"] == mk and r[key] is not None], pct))
    cut = {"zone": (q("zone", "points", 50), q("zone", "points", 200 / 3)), "dvp_pts": (q("dvp_pts", "points", 50), q("dvp_pts", "points", 200 / 3)),
           "dvp_reb": (q("dvp_reb", "rebounds", 50), q("dvp_reb", "rebounds", 200 / 3))}
    good = lambda r, key, top=False: r[key] is not None and r[key] > cut[key][1 if top else 0]
    pts_base = lambda r: r["market"] == "points" and r["mpg"] >= MIN_MPG and r["fga"] >= r["line"]
    reb_base = lambda r: r["market"] == "rebounds" and r["rc"] is not None and r["rc"] >= 2 * r["line"]
    variants = {
        "PTS ratio (FGA 1x, 20+ min)": pts_base,
        "  + zone good": lambda r: pts_base(r) and good(r, "zone"),
        "  + points-DvP good": lambda r: pts_base(r) and good(r, "dvp_pts"),
        "PTS_MATCH (+ both good)": lambda r: pts_base(r) and good(r, "zone") and good(r, "dvp_pts"),
        "  both top tercile": lambda r: pts_base(r) and good(r, "zone", True) and good(r, "dvp_pts", True),
        "REB ratio (RC 2x)": reb_base,
        "REB_MATCH (+ rebounds-DvP good)": lambda r: reb_base(r) and good(r, "dvp_reb"),
        "  + 20+ min": lambda r: reb_base(r) and good(r, "dvp_reb") and r["mpg"] >= MIN_MPG,
        "  DvP top tercile": lambda r: reb_base(r) and good(r, "dvp_reb", True)}
    res = {"cuts (2023-24 median, top tercile)": {k: [round(x, 4) for x in v] for k, v in cut.items()}, "variants": {}}
    for name, f in variants.items():
        res["variants"][name] = {s: summ([r for r in rows if r["season"] == s and f(r)]) for s in SEASONS}
    v = res["variants"]
    res["PTS_MATCH passes"] = all(v["PTS_MATCH (+ both good)"][s].get("n") and v["PTS_MATCH (+ both good)"][s]["roi"] > 0
                                  and v["PTS_MATCH (+ both good)"][s]["roi"] > v["PTS ratio (FGA 1x, 20+ min)"][s]["roi"] for s in SEASONS)
    res["REB_MATCH passes"] = all(v["REB_MATCH (+ rebounds-DvP good)"][s].get("n") and v["REB_MATCH (+ rebounds-DvP good)"][s]["roi"] > 0
                                  and v["REB_MATCH (+ rebounds-DvP good)"][s]["roi"] > v["REB ratio (RC 2x)"][s]["roi"] for s in SEASONS)
    return res


# ── forward (NBA_RATIO_PREREG.md): this season's volume as of a date, for the side-by-side at the opener ──────────
FORWARD = {"RATIO_FGA": ("points", "fga", 1.0), "RATIO_PA": ("assists", "pa", 2.0), "RATIO_RC": ("rebounds", "rc", 2.0),
           "RATIO_PA28": ("assists", "pa", 2.8)}         # amendment 3: the solver's one region positive in both seasons


class RatioData:
    """This season's per-game volume before a date: FGA from nba_matchup's box scores; potential assists and rebound
    chances from nba_tracking (a missing row on a fetched date is 0: the feeds omit zeros)."""

    def __init__(self, matchup_db, tracking_db, season):
        def ro(path):
            return sqlite3.connect(f"file:{path}?mode=ro", uri=True) if Path(path).exists() else None
        m, t = ro(matchup_db), ro(tracking_db)
        self.games = defaultdict(list)                   # pid -> [(date, fga, minutes)]
        if m is not None:
            for d, pid, fga, mn in m.execute("SELECT gm.date, p.pid, p.fga, p.min FROM player_games p JOIN games gm ON gm.gid = p.gid "
                                             "WHERE gm.season = ? AND p.min > 0", (season,)):
                self.games[pid].append((d, fga or 0.0, mn))
        self.trk, self.fetched = {}, set()
        if t is not None:
            self.fetched = {d for d, ms in t.execute("SELECT date, COUNT(DISTINCT measure) FROM fetched GROUP BY date") if ms >= 2}
            self.trk = {(d, p): (pa or 0.0, rc or 0.0) for d, p, pa, rc in t.execute("SELECT date, player_id, potential_ast, reb_chances FROM tracking")}

    def volume(self, pid, date):
        """{n, fga, pa, rc} per game over his games this season before the date (pa / rc over tracked dates), or None."""
        g = [(d, f, mn) for d, f, mn in self.games.get(pid, ()) if d < date]
        if len(g) < MIN_GAMES:
            return None
        tr = [self.trk.get((d, pid), (0.0, 0.0)) for d, _f, _m in g if d in self.fetched]
        return {"n": len(g), "fga": sum(f for _d, f, _m in g) / len(g), "mpg": sum(mn for _d, _f, mn in g) / len(g),
                "pa": sum(x[0] for x in tr) / len(tr) if tr else None, "rc": sum(x[1] for x in tr) / len(tr) if tr else None}


class DvpData:
    """Amendment 5: points allowed per game to each position group by each team this season, before a date, as a
    ratio to the league's per-team-game average for that group (nba_matchup box scores; groups from positions)."""

    def __init__(self, matchup_db, gamelogs_db, season):
        def ro(path):
            return sqlite3.connect(f"file:{path}?mode=ro", uri=True) if Path(path).exists() else None
        m, g = ro(matchup_db), ro(gamelogs_db)
        self.groups = {pid: (pos or "")[:1] or None for pid, pos in g.execute("SELECT player_id, position FROM positions")} \
            if g is not None and g.execute("SELECT 1 FROM sqlite_master WHERE name = 'positions'").fetchone() else {}
        self.games, self.box = {}, defaultdict(list)     # gid -> (date, home, away); gid -> [(team, pid, pts)]
        if m is not None:
            for gid, d, h, a in m.execute("SELECT gid, date, home, away FROM games WHERE season = ? AND home_pts IS NOT NULL", (season,)):
                self.games[gid] = (d, h, a)
            for gid, team, pid, pts in m.execute("SELECT gid, team, pid, pts FROM player_games WHERE min > 0"):
                if gid in self.games:
                    self.box[gid].append((team, pid, pts or 0))

    def dvp(self, opp, group, date):
        """The ratio, or None when the opponent has fewer than 10 games or the group is unknown."""
        if not group:
            return None
        allowed, opp_games, league, team_games = 0.0, 0, 0.0, 0
        for gid, (d, h, a) in self.games.items():
            if d >= date:
                continue
            team_games += 2
            in_game = opp in (h, a)
            opp_games += in_game
            for team, pid, pts in self.box[gid]:
                if self.groups.get(pid) == group:
                    league += pts
                    if in_game and team != opp:
                        allowed += pts
        if opp_games < 10 or not league:
            return None
        return (allowed / opp_games) / (league / team_games)


def ratio_eval(rd, spec, pid, date, market, line):
    """True when the volume in spec = (market, volume key, multiple) clears its multiple of the line."""
    mk, key, k = spec
    v = rd.volume(pid, date) if mk == market else None
    return bool(v and v[key] is not None and v[key] >= k * line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gamelogs", required=True)
    ap.add_argument("--odds", required=True)
    ap.add_argument("--tracking")
    ap.add_argument("--solve", nargs="*", metavar="RULE")
    ap.add_argument("--minutes-first", action="store_true")
    ap.add_argument("--matchup", metavar="SHOTS_DB", help="amendment 4; the zone score needs the 2023-25 shots")
    ap.add_argument("--zone-data", default=str(Path.home() / "nba-engine"), help="nba_zones' data folder")
    ap.add_argument("--json")
    a = ap.parse_args()
    if a.matchup:
        import nba_zones as Z
        res = matchup_test(build(a.gamelogs, a.odds, a.tracking), Z.build(a.matchup, Path(a.zone_data)))
        print(json.dumps(res, indent=1))
        if a.json:
            Path(a.json).write_text(json.dumps(res, indent=1))
        return
    if a.minutes_first:
        res = minutes_first(build(a.gamelogs, a.odds, a.tracking))
        print(json.dumps(res, indent=1))
        if a.json:
            Path(a.json).write_text(json.dumps(res, indent=1))
        return
    if a.solve is not None:
        rows = build(a.gamelogs, a.odds, a.tracking)
        res = {r: solve(rows, r) for r in (a.solve or ["FGA", "PA", "RC"])}
        print(json.dumps(res, indent=1))
        if a.json:
            Path(a.json).write_text(json.dumps(res, indent=1))
        return
    res = report(build(a.gamelogs, a.odds, a.tracking))
    print(json.dumps(res, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
