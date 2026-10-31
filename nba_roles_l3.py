#!/usr/bin/env python3
"""NBA_ROLES_L3_PREREG.md: do the books lag role changes? Test A (last 3 games against the season average, the Roles
tab's rule) and test B (a new starter in the first games a usual starter is out), on 2023-24 and 2024-25 tip lines.

    python3 nba_roles_l3.py [--matchup nba_matchup.sqlite] [--gamelogs nba_gamelogs.sqlite]
                            [--odds basketball_nba_odds_hist.sqlite] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
from bisect import bisect_left
from collections import defaultdict
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
SEASONS = ("2023-24", "2024-25")
PARTS = {"points": ("pts",), "rebounds": ("reb",), "assists": ("ast",), "threes": ("fg3m",), "pts_reb": ("pts", "reb"),
         "pts_ast": ("pts", "ast"), "reb_ast": ("reb", "ast"), "pra": ("pts", "reb", "ast")}
ODDS_MARKETS = {"player_points": "points", "player_rebounds": "rebounds", "player_assists": "assists",
                "player_threes": "threes", "player_points_rebounds": "pts_reb", "player_points_assists": "pts_ast",
                "player_rebounds_assists": "reb_ast", "player_points_rebounds_assists": "pra"}
SEASON_MIN_GP, RECENT_FROM = 5, 5                        # nba_players: his games, and the median team's, for "recent"
MOVE = {"min": 4.0, "fga": 3.0, "fg3a": 2.0}             # nba_players.ROLE_MOVE
USUAL_GAMES, USUAL_MIN = 10, 3                           # the usual five: most starts over the last 10 (3+ games)
A_RULES = (("A1", "min", 1, None), ("A2", "min", -1, None), ("A3 up", "fga", 1, "points"), ("A3 down", "fga", -1, "points"),
           ("A4 up", "fg3a", 1, "threes"), ("A4 down", "fg3a", -1, "threes"))
BARS = {"A1": 100, "A2": 100, "A3 up": 100, "A3 down": 100, "A4 up": 100, "A4 down": 100, "B1": 100, "B2": 50, "B1 n=2": 100}


def load_rows(matchup_db, gamelogs_db, seasons=SEASONS):
    """Box rows of players who played: starter flags from nba_matchup, FGA/3PA/threes from nba_gamelogs."""
    c = sqlite3.connect(f"file:{matchup_db}?mode=ro", uri=True)
    c.execute("ATTACH ? AS g", (f"file:{gamelogs_db}?mode=ro",))
    q = ("SELECT g0.season, p.gid, g0.date, p.team, p.pid, p.starter, p.min, p.pts, p.reb, p.ast, l.fg3m, l.fga, l.fg3a "
         "FROM player_games p JOIN games g0 ON g0.gid = p.gid JOIN g.logs_full l ON l.game_id = p.gid AND l.player_id = p.pid "
         "WHERE g0.season IN (%s) AND p.min > 0" % ",".join("?" * len(seasons)))
    cols = ("season", "gid", "date", "team", "pid", "starter", "min", "pts", "reb", "ast", "fg3m", "fga", "fg3a")
    return [dict(zip(cols, r)) for r in c.execute(q, seasons)]


def tip_lines(gamelogs_db, odds_db):
    """{(date, pid, market): (line, best over, best under, no-vig over)} at the main rung (the over nearest even money
    at FanDuel or DraftKings, both sides posted)."""
    import nba_margin_refit as MR
    g = sqlite3.connect(f"file:{gamelogs_db}?mode=ro", uri=True)
    name2pid = {MR.norm(nm): pid for pid, nm in g.execute("SELECT DISTINCT player_id, player FROM logs_full")}
    o = sqlite3.connect(f"file:{odds_db}?immutable=1", uri=True)
    raw = defaultdict(lambda: defaultdict(dict))
    q = ("SELECT game_date, player, market, line, side, price, book FROM props WHERE snap_kind = 'tip' AND market IN (%s) "
         "AND price IS NOT NULL AND line IS NOT NULL AND book IN ('fanduel', 'draftkings')" % ",".join("?" * len(ODDS_MARKETS)))
    for d, pl, m, line, side, price, book in o.execute(q, tuple(ODDS_MARKETS)):
        pid = name2pid.get(MR.norm(pl))
        if pid is not None:
            raw[(d, pid, ODDS_MARKETS[m])][float(line)].setdefault(book, [None, None])[0 if side == "over" else 1] = float(price)
    return {k: v for k, lb in raw.items() if (v := main_rung(lb))}


def main_rung(lb):
    """{line: {book: [over, under]}} -> (line, best over, best under, FanDuel's no-vig over, else DraftKings')."""
    best = None
    for line, bk in lb.items():
        two = {b: v for b, v in bk.items() if v[0] and v[1]}
        if two:
            gap = min(abs(v[0] - 2.0) for v in two.values())
            if best is None or gap < best[0] - 1e-9:
                best = (gap, line, two)
    if not best:
        return None
    _g, line, two = best
    pair = two.get("fanduel") or two.get("draftkings")
    return line, max(v[0] for v in two.values()), max(v[1] for v in two.values()), (1 / pair[0]) / (1 / pair[0] + 1 / pair[1])


def stat(row, market):
    return sum(row[s] or 0 for s in PARTS[market])


def grade(actual, line, side, over, under, nv):
    """One bet: u per unit (win at the price, push 0, loss -1), and the side's no-vig probability."""
    price, p = (over, nv) if side == "over" else (under, 1 - nv)
    if actual == line:
        return 0.0, p, None
    win = actual > line if side == "over" else actual < line
    return (price - 1 if win else -1.0), p, win


class Season:
    """One season's boxes. Every question takes tonight's date and reads only games before it (B's starter flag aside)."""

    def __init__(self, rows, season):
        self.season = season
        box = defaultdict(dict)                          # (team, date, gid) -> {pid: row}
        for r in rows:
            if r["season"] == season:
                box[(r["team"], r["date"], r["gid"])][r["pid"]] = r
        self.games = defaultdict(list)                   # team -> [(date, gid, {pid: row})] by date
        for (t, d, g), b in box.items():
            self.games[t].append((d, g, b))
        for v in self.games.values():
            v.sort(key=lambda x: (x[0], x[1]))
        apps = defaultdict(list)                         # pid -> [(date, team, gid)]
        for t, gs in self.games.items():
            for d, g, b in gs:
                for p in b:
                    apps[p].append((d, t, g))
        self.apps = {p: sorted(v) for p, v in apps.items()}
        self.dates = sorted({d for gs in self.games.values() for d, _g, _b in gs})
        self.cache = {}

    def before(self, team, date):
        g = self.games.get(team, [])
        return g[:bisect_left(g, (date,))]

    def median_gp(self, date):
        if date not in self.cache:
            gp = sorted(len(self.before(t, date)) for t in self.games)
            self.cache[date] = gp[len(gp) // 2] if gp else 0
        return self.cache[date]

    def moves(self, pid, team, date):
        """{stat: L3 - S} for test A (S over all his games for the team this season before tonight, the last 3
        included), or None when he has under SEASON_MIN_GP games or isn't playing lately."""
        prior = self.before(team, date)
        mine = [(g, b[pid]) for _d, g, b in prior if pid in b]
        if len(mine) < SEASON_MIN_GP or self.median_gp(date) < RECENT_FROM:
            return None
        last4 = {g for _d, g, _b in prior[-4:]}
        if any(g not in last4 for g, _r in mine[-3:]):
            return None
        rs = [r for _g, r in mine]
        out = {}
        for k in MOVE:
            now, was = [r[k] for r in rs[-3:] if r[k] is not None], [r[k] for r in rs if r[k] is not None]
            out[k] = sum(now) / len(now) - sum(was) / len(was) if len(now) == 3 and was else None
        return out

    def last_team(self, pid, date):
        """The team of his last game before tonight."""
        a = self.apps.get(pid, [])
        i = bisect_left(a, (date,))
        return a[i - 1][1] if i else None

    def on_team(self, pid, team, date):
        """He was on the team tonight: his last game before tonight and his next one after, if any, were for it."""
        a = self.apps.get(pid, [])
        i = bisect_left(a, (date,))
        if not i or a[i - 1][1] != team:
            return False
        nxt = [x for x in a[i:] if x[0] > date]
        return not nxt or nxt[0][1] == team

    def usual_five(self, team, date):
        """The 5 on the team (their last game before tonight was for it) with the most starts in its last 10 games
        (ties: more minutes), a start needed; None under 3 games."""
        recent = self.before(team, date)[-USUAL_GAMES:]
        if len(recent) < USUAL_MIN:
            return None
        starts, mins = defaultdict(int), defaultdict(float)
        for _d, _g, b in recent:
            for p, r in b.items():
                if self.last_team(p, date) == team:
                    starts[p] += r["starter"] or 0
                    mins[p] += r["min"]
        return {p for p in sorted(starts, key=lambda p: (-starts[p], -mins[p], p))[:5] if starts[p]}

    def tonight(self, team, date):
        for d, _g, b in self.games.get(team, []):
            if d == date:
                return b
        return {}

    def absence_n(self, pid, team, date):
        """Team games in a row he has missed, tonight included."""
        n = 1
        for _d, _g, b in reversed(self.before(team, date)):
            if pid in b:
                break
            n += 1
        return n

    def missing(self, team, date, five):
        """{X: absence game n} for the usual five who are out tonight (on the team, not in tonight's box)."""
        box = self.tonight(team, date)
        if not five:
            return {}
        return {x: self.absence_n(x, team, date) for x in five if x not in box and self.on_team(x, team, date)}

    def prev_game(self, pid, date):
        a = self.apps.get(pid, [])
        i = bisect_left(a, (date,))
        return a[i - 1] if i else None

    def next_team_game(self, team, date):
        g = self.games.get(team, [])
        i = bisect_left(g, (date,))
        while i < len(g) and g[i][0] <= date:
            i += 1
        return g[i] if i < len(g) else None


def run(rows, lines, seasons=SEASONS):
    by_date = defaultdict(list)
    for (d, pid, mk), v in lines.items():
        by_date[(d, pid)].append((mk, v))
    bets, info = [], defaultdict(list)
    for s in seasons:
        S = Season(rows, s)
        for team, gs in S.games.items():
            for d, gid, box in gs:
                five = S.usual_five(team, d) or set()
                miss = S.missing(team, d, five)
                n_min = min(miss.values()) if miss else None
                for pid, r in box.items():
                    ls = by_date.get((d, pid))
                    if not ls:
                        continue
                    base = {"season": s, "date": d, "team": team, "pid": pid}
                    mv = S.moves(pid, team, d)
                    for name, k, sign, only in A_RULES:
                        if mv and mv[k] is not None and sign * mv[k] >= MOVE[k]:
                            for mk, v in ls:
                                if only in (None, mk):
                                    bets.append(bet(base, name, mk, v, r, "over" if sign > 0 else "under"))
                    if n_min is None:
                        continue
                    new_starter = r["starter"] and pid not in five
                    for mk, v in ls:
                        if n_min == 1:
                            info["every teammate, n=1"].append(bet(base, "every teammate, n=1", mk, v, r, "over"))
                        if not new_starter or n_min > 3:
                            continue
                        name = "B1" if n_min == 1 else f"B1 n={n_min}"
                        b = bet(base, name, mk, v, r, "over")
                        (bets if n_min <= 2 else info[name]).append(b)
                        if n_min != 1:
                            continue
                        pg = S.prev_game(pid, d)
                        prev = lines.get((pg[0], pid, mk)) if pg else None
                        if prev and v[0] <= prev[0]:
                            bets.append({**b, "rule": "B2"})
                        nxt = S.next_team_game(team, d)
                        nl = lines.get((nxt[0], pid, mk)) if nxt and pid in nxt[2] else None
                        x1 = [x for x, n in miss.items() if n == 1]
                        info["bump"].append({"season": s, "market": mk, "prev": prev[0] if prev else None, "g1": v[0],
                                             "g2": nl[0] if nl and all(x not in nxt[2] for x in x1) else None})
    return bets, info


def bet(base, rule, mk, v, r, side):
    line, over, under, nv = v
    act = stat(r, mk)
    u, p, win = grade(act, line, side, over, under, nv)
    return {**base, "rule": rule, "market": mk, "side": side, "line": line, "actual": act, "u": u, "p": p, "win": win}


def summ(bs, boot=0):
    if not bs:
        return {"n": 0}
    dec = [b for b in bs if b["win"] is not None]
    out = {"n": len(bs), "games": len({(b["date"], b["pid"]) for b in bs}),
           "hit": round(sum(b["win"] for b in dec) / len(dec), 4) if dec else None,
           "nv": round(sum(b["p"] for b in bs) / len(bs), 4), "roi": round(sum(b["u"] for b in bs) / len(bs), 4)}
    if boot:
        cl = defaultdict(list)                           # one player's markets on a night move together
        for b in bs:
            cl[(b["date"], b["pid"])].append(b["u"])
        cs, rng, rs = list(cl.values()), random.Random(7), []
        for _ in range(boot):
            pick = [rng.choice(cs) for _ in cs]
            rs.append(sum(map(sum, pick)) / sum(map(len, pick)))
        rs.sort()
        out["roi90"] = [round(rs[int(0.05 * boot)], 4), round(rs[int(0.95 * boot)], 4)]
    return out


def passes(per_season, bar):
    return all(x["n"] >= bar and x["roi"] > 0 and x["hit"] is not None and x["hit"] > x["nv"] for x in per_season)


def report(bets, info, seasons=SEASONS):
    res = {"rules": {}, "info": {}}
    for rule in BARS:
        bs = [b for b in bets if b["rule"] == rule]
        per = {s: summ([b for b in bs if b["season"] == s], boot=1000) for s in seasons}
        res["rules"][rule] = {"season": per, "pass": passes(per.values(), BARS[rule]),
                              "market": {s: {m: summ([b for b in bs if b["season"] == s and b["market"] == m]) for m in PARTS}
                                         for s in seasons}}
    for k in ("every teammate, n=1", "B1 n=3"):
        res["info"][k] = {s: summ([b for b in info[k] if b["season"] == s]) for s in seasons}
    bump = {}
    for s in seasons:
        bs = [b for b in info["bump"] if b["season"] == s]
        d1 = [b["g1"] - b["prev"] for b in bs if b["prev"] is not None]
        d2 = [b["g2"] - b["g1"] for b in bs if b["g2"] is not None]
        bump[s] = {"prev_to_g1": [len(d1), round(sum(d1) / len(d1), 2) if d1 else None, median(d1) if d1 else None],
                   "g1_to_g2": [len(d2), round(sum(d2) / len(d2), 2) if d2 else None, median(d2) if d2 else None],
                   "points_prev_to_g1": mean_of([b["g1"] - b["prev"] for b in bs if b["prev"] is not None and b["market"] == "points"]),
                   "points_g1_to_g2": mean_of([b["g2"] - b["g1"] for b in bs if b["g2"] is not None and b["market"] == "points"])}
    res["info"]["line_bump"] = bump
    return res


def mean_of(xs):
    return [len(xs), round(sum(xs) / len(xs), 2) if xs else None]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--matchup", default=str(HERE / "nba_matchup.sqlite"))
    ap.add_argument("--gamelogs", default=str(HERE / "nba_gamelogs.sqlite"))
    ap.add_argument("--odds", default=str(HERE / "basketball_nba_odds_hist.sqlite"))
    ap.add_argument("--json")
    a = ap.parse_args()
    rows = load_rows(a.matchup, a.gamelogs)
    lines = tip_lines(a.gamelogs, a.odds)
    bets, info = run(rows, lines)
    res = report(bets, info)
    played = defaultdict(int)
    for r in rows:
        if r["min"] >= 20:
            played[r["season"]] += 1
    res["coverage"] = {s: round(sum(1 for r in rows if r["season"] == s and r["min"] >= 20 and
                                    any((r["date"], r["pid"], m) in lines for m in ("points",))) / played[s], 3) for s in SEASONS}
    print(json.dumps({k: v for k, v in res.items()}, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
