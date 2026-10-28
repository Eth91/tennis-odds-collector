#!/usr/bin/env python3
"""BOOST (NBA_BOOST_PREREG.md): players who gain when a starter is out, judged against tonight's line.

A starter (26+ min/g) is out tonight, in the first 3 games of his absence. A teammate is flagged on the over when, in
past games without that starter but with tonight's other starters (this season and last, same team), he averaged 20+
minutes and beat tonight's line in 80%+ of them (3+ games; 6+ when the starter's own numbers say he does not matter
for the market). With fewer than 3 such games, the position rules alone: the starter's share redistributed (3x to his
position group) must put the teammate 15%+ over the line. Overs priced -150 or better.

    python3 nba_boost.py --gamelogs .projdata/nba_gamelogs.sqlite --odds ~/nba-engine/basketball_nba_odds_hist.sqlite [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
from bisect import bisect_left
from collections import defaultdict
from pathlib import Path

STARTER_MIN, BASE_THIS, BASE_LAST, SPOT_MAX = 26.0, 3, 10, 3
MIN_H, MIN_H_IRRELEVANT, HIT_AT, MIN_AVG_MIN = 3, 6, 0.80, 20.0
PROJ_AT, BASE_N, BASE_MIN_GAMES, SAME_W, PRICE_MIN = 1.15, 10, 3, 3.0, 1 / 0.6   # -150 = decimal 1.6667
STEP_MIN = 24.0                                          # amendment 2: the step-in player's minutes floor
TOP = {"reb": ("reb", 2), "pts": ("fga", 3), "fg3m": ("fga", 3), "ast": ("ast", 2)}   # stat -> (ranked by, top n)
PARTS = {"points": ("pts",), "rebounds": ("reb",), "assists": ("ast",), "threes": ("fg3m",), "pts_reb": ("pts", "reb"),
         "pts_ast": ("pts", "ast"), "reb_ast": ("reb", "ast"), "pra": ("pts", "reb", "ast")}
ODDS_MARKETS = {"player_points": "points", "player_rebounds": "rebounds", "player_assists": "assists",
                "player_threes": "threes", "player_points_rebounds": "pts_reb", "player_points_assists": "pts_ast",
                "player_rebounds_assists": "reb_ast", "player_points_rebounds_assists": "pra"}
SEASONS = ("2023-24", "2024-25")
PREV = {"2023-24": "2022-23", "2024-25": "2023-24", "2025-26": "2024-25", "2026-27": "2025-26"}
FDK = ("fanduel", "draftkings")
COLS = ("season", "gid", "date", "team", "pid", "min", "fga", "fg3m", "reb", "ast", "pts")


def group(pos):
    return (pos or "")[:1] or None


class BoostData:
    """Two seasons of box rows (this one and last). Every question takes tonight's date and reads only games before it."""

    def __init__(self, rows, groups, season):
        self.season, self.groups = season, groups
        by = defaultdict(dict)
        for r in rows:
            by[(r["team"], r["date"], r["gid"], r["season"])][r["pid"]] = r
        self.games = defaultdict(list)                   # team -> [(date, gid, season, {pid: row}), ...] by date
        for (team, d, g, s), box in by.items():
            self.games[team].append((d, g, s, box))
        for v in self.games.values():
            v.sort(key=lambda x: (x[0], x[1]))
        apps = defaultdict(list)                         # pid -> [(date, team)] for games played (min > 0)
        for r in rows:
            if r["min"]:
                apps[r["pid"]].append((r["date"], r["team"]))
        self.apps = {p: sorted(v) for p, v in apps.items()}
        self.cache = {}

    def before(self, team, date):
        g = self.games.get(team, [])
        return g[:bisect_left(g, (date,))]

    def team_now(self, pid, date):
        """The team of his last appearance before the date."""
        a = self.apps.get(pid, [])
        i = bisect_left(a, (date,))
        return a[i - 1][1] if i else None

    def on_team_at(self, x, team, d_game, date):
        """X was on the team at a past game he missed: his last appearance before it and his next one (before tonight),
        if any, were for the team."""
        a = self.apps.get(x, [])
        i = bisect_left(a, (d_game,))
        if not i or a[i - 1][1] != team or (i < len(a) and a[i][0] == d_game):
            return False                                 # not with the team before it, or played elsewhere that day
        return i >= len(a) or a[i][0] >= date or a[i][1] == team

    def base_rows(self, pid, team, date):
        """His games for the team this season if 3+, else last season's if 10+, else none (rule 1)."""
        mine = [b[pid] for _d, _g, _s, b in self.before(team, date) if pid in b and b[pid]["min"]]
        this = [r for r in mine if r["season"] == self.season]
        if len(this) >= BASE_THIS:
            return this
        last = [r for r in mine if r["season"] != self.season]
        return last if len(last) >= BASE_LAST else []

    def per_game(self, pid, team, date):
        k = ("pg", pid, team, date)
        if k not in self.cache:
            rs = self.base_rows(pid, team, date)
            self.cache[k] = {s: sum(r[s] or 0 for r in rs) / len(rs) for s in ("min", "fga", "reb", "ast", "pts", "fg3m")} if rs else None
        return self.cache[k]

    def on_team_tonight(self, team, date):
        k = ("on", team, date)
        if k not in self.cache:
            seen = {p for _d, _g, _s, b in self.before(team, date) for p in b}
            self.cache[k] = {p for p in seen if self.team_now(p, date) == team}
        return self.cache[k]

    def starters(self, team, date):
        k = ("st", team, date)
        if k not in self.cache:
            self.cache[k] = {p for p in self.on_team_tonight(team, date)
                             if (pg := self.per_game(p, team, date)) and pg["min"] >= STARTER_MIN}
        return self.cache[k]

    def absence_n(self, x, team, date):
        n = 1
        for _d, _g, _s, b in reversed(self.before(team, date)):
            if x in b and b[x]["min"]:
                return n
            n += 1
        return n

    def relevant(self, x, team, date):
        """{stat: True} where X is in the team's top n by his own per-game numbers (rule 6)."""
        k = ("rel", x, team, date)
        if k not in self.cache:
            pgs = {p: pg for p in self.on_team_tonight(team, date) if (pg := self.per_game(p, team, date))}
            out = {}
            for s, (by, top) in TOP.items():
                ranked = sorted(pgs, key=lambda p: -pgs[p][by])
                out[s] = x in ranked[:top]
            self.cache[k] = out
        return self.cache[k]

    def history(self, b, x, team, date, others):
        """Past team games where B played, X was on the team and did not play, and every other starter playing tonight
        played (rule 8)."""
        out = []
        for d, _g, _s, box in self.before(team, date):
            if b in box and box[b]["min"] and not (x in box and box[x]["min"]) and \
                    all(o in box and box[o]["min"] for o in others) and self.on_team_at(x, team, d, date):
                out.append(box[b])
        return out

    def roster(self, team, date):
        return {p for _d, _g, _s, b in self.before(team, date)[-3:] for p, r in b.items() if r["min"]}

    def base_with(self, pid, x, team, date, others=()):
        """Per-game averages over his last 10 games for the team in which X and the other starters playing tonight
        (`others`) played: this season's if 3+, else last season's if 3+, else None (amendment 2)."""
        rs = [(s, b[pid]) for _d, _g, s, b in self.before(team, date) if all(q in b and b[q]["min"] for q in (pid, x, *others))]
        this = [r for s, r in rs if s == self.season]
        rs = (this if len(this) >= BASE_MIN_GAMES else [r for s, r in rs if s != self.season])[-BASE_N:]
        if len(rs) < BASE_MIN_GAMES:
            return None
        return {s: sum(r[s] or 0 for r in rs) / len(rs) for s in ("min", "reb", "ast", "pts", "fg3m")}

    def step_in(self, x, team, date, out_all):
        """The active non-starter in X's position group with the most minutes per game over his base games (amendment 2)."""
        gx = self.groups.get(x)
        cands = [(pg["min"], p) for p in self.roster(team, date) - set(out_all) - self.starters(team, date)
                 if gx and self.groups.get(p) == gx and (pg := self.per_game(p, team, date))]
        return max(cands)[1] if cands else None

    def projection(self, b, x, team, date, out_all):
        """{stat: projection} for B with X's per-game numbers redistributed over the active roster, 3x to X's position
        group (rule 10). Bases come from games with tonight's other starters, and the step-in player gets 24+ minutes
        (amendment 2). None when B or X has no base."""
        k = ("proj", x, team, date, frozenset(out_all))
        if k not in self.cache:
            xs = self.per_game(x, team, date)
            playing = self.starters(team, date) - set(out_all)
            bases = {p: bw for p in self.roster(team, date) - set(out_all)
                     if (bw := self.base_with(p, x, team, date, sorted(playing - {p})))}
            w = {p: SAME_W if self.groups.get(p) and self.groups.get(p) == self.groups.get(x) else 1.0 for p in bases}
            proj = {}
            for p, bw in bases.items():
                proj[p] = {}
                for s in bw:
                    tot = sum(bases[a][s] * w[a] for a in bases)
                    proj[p][s] = bw[s] + (xs[s] * bw[s] * w[p] / tot if xs and tot else 0.0)
            step = self.step_in(x, team, date, out_all)
            if step in proj and proj[step]["min"] < STEP_MIN and bases[step]["min"]:
                add = STEP_MIN - proj[step]["min"]       # he starts: 24 minutes at least, at his own per-minute rates
                for s in proj[step]:
                    proj[step][s] += add * bases[step][s] / bases[step]["min"]
                proj[step]["step"] = 1.0                 # amendment 3: a STEP flag
            self.cache[k] = proj if xs else {}
        return self.cache[k].get(b)


def stat_of(row, market):
    return sum(row[s] or 0 for s in PARTS[market])


def boost_eval(bd, date, team, pid, market, line, price, out_all):
    """The flag for one prop (rules 4-13), or None. out_all: everyone on the team out tonight."""
    if price is None or price < PRICE_MIN - 1e-9 or pid in out_all:
        return None
    starters = bd.starters(team, date)
    best = None
    for x in sorted(starters & set(out_all)):
        if x == pid:
            continue
        n = bd.absence_n(x, team, date)
        if n > SPOT_MAX:
            continue
        rel = any(bd.relevant(x, team, date)[s] for s in PARTS[market])
        hk = ("hist", pid, x, team, date, frozenset(out_all))
        if hk not in bd.cache:
            bd.cache[hk] = bd.history(pid, x, team, date, starters - set(out_all) - {pid, x})
        hist = bd.cache[hk]
        cand = None
        if len(hist) >= MIN_H:
            hits = sum(stat_of(r, market) > line for r in hist)
            avg_min = sum(r["min"] for r in hist) / len(hist)
            if avg_min >= MIN_AVG_MIN and hits / len(hist) >= HIT_AT - 1e-9 and (rel or len(hist) >= MIN_H_IRRELEVANT):
                cand = {"kind": "history", "x": x, "n": n, "hits": hits, "h": len(hist), "relevant": rel,
                        "avg": sum(stat_of(r, market) for r in hist) / len(hist), "avg_min": avg_min}
        elif rel:
            pr = bd.projection(pid, x, team, date, out_all)
            if pr:
                mu = sum(pr[s] for s in PARTS[market])
                if mu >= PROJ_AT * line and pr["min"] >= MIN_AVG_MIN:
                    cand = {"kind": "no history", "x": x, "n": n, "h": len(hist), "relevant": rel, "proj": mu, "proj_min": pr["min"],
                            "step": bool(pr.get("step"))}
        if cand and (best is None or rank(cand) > rank(best)):
            best = cand
    return best


def rank(c):
    return (c["kind"] == "history", c["hits"] / c["h"] if c["kind"] == "history" else 0.0, bool(c.get("step")), c["h"])


def kind_of(f):
    """The registered rule a flag belongs to (amendment 3)."""
    return "history" if f["kind"] == "history" else "step" if f.get("step") else "no history"


# ── live ──────────────────────────────────────────────────────────────────────────────────────────────────────────
ABBR = {"points": "PTS", "rebounds": "REB", "assists": "AST", "threes": "3PM", "pts_reb": "P+R", "pts_ast": "P+A",
        "reb_ast": "R+A", "pra": "PRA"}


def live_data(matchup_db, gamelogs_db, season):
    """This season's box scores (nba_matchup) and last season's logs (nba_gamelogs logs_full), as ROLE's RoleData reads them."""
    ro = lambda p: sqlite3.connect(f"file:{p}?mode=ro", uri=True) if Path(p).exists() else None
    has = lambda c, t: c is not None and c.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (t,)).fetchone()
    m, g = ro(matchup_db), ro(gamelogs_db)
    rows = [dict(zip(COLS, r)) for r in m.execute(
        "SELECT gm.season, p.gid, gm.date, p.team, p.pid, p.min, p.fga, p.fg3m, p.reb, p.ast, p.pts FROM player_games p "
        "JOIN games gm ON gm.gid = p.gid WHERE gm.season = ?", (season,))] if has(m, "player_games") else []
    if has(g, "logs_full"):
        rows += [dict(zip(COLS, r)) for r in g.execute(
            "SELECT season, game_id, date, team, player_id, min, fga, fg3m, reb, ast, pts FROM logs_full WHERE season = ?",
            (PREV.get(season, ""),))]
    for r in rows:
        r["min"] = r["min"] or 0.0
    groups = {pid: group(pos) for pid, pos in g.execute("SELECT player_id, position FROM positions")} if has(g, "positions") else {}
    return BoostData(rows, groups, season)


def body(player, market, line, price, book, f, x_name):
    from nba_ping import american
    k = kind_of(f)
    why = (f"{f['hits']}/{f['h']} beat {line:g} without him, avg {f['avg']:.1f}" if k == "history"
           else f"steps in, proj {f['proj']:.1f} at {STEP_MIN:g} min" if k == "step" else f"no history, proj {f['proj']:.1f}")
    return (f"🟢 BOOST{' STEP' if k == 'step' else ''} {player} {ABBR[market]} o{line:g} {american(price)} {book} · {x_name} "
            f"out (game {f['n']}) · {why} · shadow")


# ── the backtest ──────────────────────────────────────────────────────────────────────────────────────────────────
def load_rows(gamelogs_db, seasons):
    g = sqlite3.connect(f"file:{gamelogs_db}?mode=ro", uri=True)
    q = ("SELECT season, game_id, date, team, player_id, min, fga, fg3m, reb, ast, pts FROM logs_full WHERE season IN (%s)"
         % ",".join("?" * len(seasons)))
    rows = [dict(zip(COLS, r)) for r in g.execute(q, seasons)]
    for r in rows:
        r["min"] = r["min"] or 0.0
    groups = {pid: group(pos) for pid, pos in g.execute("SELECT player_id, position FROM positions")}
    return rows, groups


def tip_lines(gamelogs_db, odds_db):
    """{(date, pid, market): (line, best FanDuel/DraftKings over, no-vig over)} at the main rung (the over nearest even)."""
    import nba_margin_refit as MR
    g = sqlite3.connect(f"file:{gamelogs_db}?mode=ro", uri=True)
    name2pid = {MR.norm(nm): pid for pid, nm in g.execute("SELECT DISTINCT player_id, player FROM logs_full")}
    o = sqlite3.connect(f"file:{odds_db}?mode=ro", uri=True)
    raw = defaultdict(lambda: defaultdict(dict))
    q = ("SELECT game_date, player, market, line, side, price, book FROM props WHERE market IN (%s) AND price IS NOT NULL "
         "AND line IS NOT NULL AND book IN ('fanduel', 'draftkings')" % ",".join("?" * len(ODDS_MARKETS)))
    for d, pl, m, line, side, price, book in o.execute(q, tuple(ODDS_MARKETS)):
        pid = name2pid.get(MR.norm(pl))
        if pid is not None:
            raw[(d, pid, ODDS_MARKETS[m])][float(line)].setdefault(book, [None, None])[0 if side == "over" else 1] = float(price)
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
            out[k] = (line, max(v[0] for v in two.values()), (1 / pair[0]) / (1 / pair[0] + 1 / pair[1]))
    return out


def backtest(gamelogs_db, odds_db, seasons=SEASONS):
    lines = tip_lines(gamelogs_db, odds_db)
    by_date = defaultdict(list)
    for (d, pid, mk), v in lines.items():
        by_date[d].append((pid, mk, v))
    flags = []
    for s in seasons:
        rows, groups = load_rows(gamelogs_db, (PREV[s], s))
        bd = BoostData(rows, groups, s)
        tonight = defaultdict(dict)                      # (date, team) -> {pid: row}: this season's boxes
        for r in rows:
            if r["season"] == s:
                tonight[(r["date"], r["team"])][r["pid"]] = r
        for (d, team), box in sorted(tonight.items()):
            played = {p for p, r in box.items() if r["min"]}
            on = bd.on_team_tonight(team, d)
            out_all = (on - played) & (bd.roster(team, d) | bd.starters(team, d))
            if not (bd.starters(team, d) & out_all):
                continue
            for pid, mk, (line, over, nv) in by_date.get(d, ()):
                if pid not in played:
                    continue                             # not in tonight's box for this team: void or another team
                f = boost_eval(bd, d, team, pid, mk, line, over, out_all)
                if f:
                    act = stat_of(box[pid], mk)
                    u = (over - 1) if act > line else (0.0 if act == line else -1.0)
                    flags.append({**f, "season": s, "date": d, "team": team, "pid": pid, "market": mk, "line": line,
                                  "price": over, "nv": nv, "actual": act, "u": u})
    return flags


def summ(fs, boot=0):
    if not fs:
        return {"n": 0}
    np_ = [f for f in fs if f["actual"] != f["line"]]
    out = {"n": len(fs), "hit": round(sum(f["actual"] > f["line"] for f in np_) / len(np_), 4) if np_ else None,
           "nv": round(sum(f["nv"] for f in fs) / len(fs), 4), "roi": round(sum(f["u"] for f in fs) / len(fs), 4)}
    if boot:
        rng, us = random.Random(7), [f["u"] for f in fs]
        bs = sorted(sum(rng.choice(us) for _ in us) / len(us) for _ in range(boot))
        out["roi90"] = [round(bs[int(0.05 * boot)], 4), round(bs[int(0.95 * boot)], 4)]
    return out


def report(flags):
    res = {}
    for s in sorted({f["season"] for f in flags} | set(SEASONS)):
        fs = [f for f in flags if f["season"] == s]
        res[s] = {"all": summ(fs, boot=2000),
                  "kind": {k: summ([f for f in fs if kind_of(f) == k]) for k in ("history", "step", "no history")},
                  "market": {m: summ([f for f in fs if f["market"] == m]) for m in PARTS},
                  "absence_game": {n: summ([f for f in fs if f["n"] == n]) for n in (1, 2, 3)},
                  "relevance": {"relevant": summ([f for f in fs if f["relevant"]]),
                                "irrelevant, 6+ games": summ([f for f in fs if not f["relevant"]])}}
    res["pass"] = all(res[s]["all"]["n"] >= 100 and res[s]["all"]["roi"] > 0 for s in SEASONS)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gamelogs", default=".projdata/nba_gamelogs.sqlite")
    ap.add_argument("--odds", default=str(Path.home() / "nba-engine" / "basketball_nba_odds_hist.sqlite"))
    ap.add_argument("--json")
    a = ap.parse_args()
    flags = backtest(a.gamelogs, a.odds)
    res = report(flags)
    print(json.dumps(res, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps({"result": res, "flags": flags}, indent=1, default=str))


if __name__ == "__main__":
    main()
