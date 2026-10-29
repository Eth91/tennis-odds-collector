#!/usr/bin/env python3
"""Six basketball-logic ideas (NBA_IDEAS_PREREG.md), backtested at the archive's tip lines (2023-24, 2024-25). Every
feature is season to date, strictly before the game's date. Idea 5 (minutes restrictions) is forward only.

    python3 nba_ideas.py --gamelogs .projdata/nba_gamelogs.sqlite --odds ~/nba-engine/basketball_nba_odds_hist.sqlite \
        --matchup ~/nba-engine/nba_matchup.sqlite --tracking .projdata/tracking_hist.sqlite [--json OUT]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

import nba_margin_refit as MR

SEASONS = ("2023-24", "2024-25")
FDK = ("fanduel", "draftkings")
MKT = {"player_points": "points", "player_rebounds": "rebounds", "player_assists": "assists", "player_points_rebounds_assists": "pra"}
HOME_EDGE = 2.5


def main_rung(lb):
    """(line, best over, best under) at the two-sided FanDuel/DraftKings rung whose over is nearest even money."""
    best = None
    for line, bk in lb.items():
        two = [v for b, v in bk.items() if b in FDK and v[0] and v[1]]
        if two:
            gap = min(abs(v[0] - 2.0) for v in two)
            if best is None or gap < best[0] - 1e-9:
                best = (gap, line, max(v[0] for v in two), max(v[1] for v in two))
    return best[1:] if best else None


def build(gamelogs_db, odds_db, matchup_db, tracking_db=None):
    g = sqlite3.connect(f"file:{gamelogs_db}?mode=ro", uri=True)
    name2pid = {MR.norm(nm): pid for pid, nm in g.execute("SELECT DISTINCT player_id, player FROM logs_full")}
    groups = {pid: (pos or "")[:1] or None for pid, pos in g.execute("SELECT player_id, position FROM positions")}
    m = sqlite3.connect(f"file:{matchup_db}?mode=ro", uri=True)
    home_of = {gid: h for gid, h in m.execute("SELECT gid, home FROM games")}
    trk = {}
    if tracking_db and Path(tracking_db).exists():
        t = sqlite3.connect(f"file:{tracking_db}?mode=ro", uri=True)
        trk = {(d, p): rc or 0.0 for d, p, rc in t.execute("SELECT date, player_id, reb_chances FROM tracking")}
        tracked = {d for (d,) in t.execute("SELECT DISTINCT date FROM fetched")}
    o = sqlite3.connect(f"file:{odds_db}?mode=ro", uri=True)
    raw = defaultdict(lambda: defaultdict(dict))
    for d, pl, mk, line, side, price, book in o.execute(
            f"SELECT game_date, player, market, line, side, price, book FROM props WHERE market IN ({','.join('?' * len(MKT))}) "
            f"AND price IS NOT NULL AND line IS NOT NULL", list(MKT)):
        if book in FDK:
            raw[(d, name2pid.get(MR.norm(pl)), MKT[mk])][float(line)].setdefault(book, [None, None])[0 if side == "over" else 1] = float(price)
    rows = []
    for s in SEASONS:
        games = defaultdict(lambda: defaultdict(dict))   # date -> gid -> {pid: box}
        for d, gid, team, pid, mn, fgm, fga, fta, pf, pts, reb, ast in g.execute(
                "SELECT date, game_id, team, player_id, min, fgm, fga, fta, pf, pts, reb, ast FROM logs_full WHERE season = ?", (s,)):
            games[d][gid][pid] = {"team": team, "min": mn or 0.0, "fgm": fgm or 0, "fga": fga or 0, "fta": fta or 0, "pf": pf or 0,
                                  "pts": pts or 0, "reb": reb or 0, "ast": ast or 0}
        P = defaultdict(lambda: {"n": 0, "min": 0.0, "pf": 0.0, "rc": 0.0, "n_trk": 0})        # player season totals
        T = defaultdict(lambda: {"n": 0, "for": 0.0, "against": 0.0, "fta": 0.0, "miss": 0.0, "dates": [], "box": []})
        for d in sorted(games):
            day = games[d]
            prev = (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat()
            for gid, box in day.items():
                teams = sorted({r["team"] for r in box.values()})
                if len(teams) != 2:
                    continue
                home = home_of.get(gid)
                ratings = {}
                for tm in teams:
                    st = T[tm]
                    ratings[tm] = (st["for"] / st["n"], st["against"] / st["n"]) if st["n"] >= 10 else None
                for tm in teams:
                    opp = teams[1] if tm == teams[0] else teams[0]
                    st, so = T[tm], T[opp]
                    b2b = prev in st["dates"]
                    opp_fta = so["fta"] / so["n"] if so["n"] >= 10 else None
                    opp_miss = so["miss"] / so["n"] if so["n"] >= 10 else None
                    pm = ptot = None
                    if ratings[tm] and ratings[opp]:
                        (f1, a1), (f2, a2) = ratings[tm], ratings[opp]
                        pm = ((f1 - a1) - (f2 - a2)) / 2 + (HOME_EDGE if tm == home else -HOME_EDGE)
                        ptot = (f1 + a2 + f2 + a1) / 2
                    returning = _returning(st["box"], {p for p, r in box.items() if r["team"] == tm and r["min"]})
                    for pid, r in box.items():
                        if r["team"] != tm or not r["min"]:
                            continue
                        ps = P[(s, pid)]
                        if ps["n"] < 5:
                            continue
                        for mk in ("points", "rebounds", "assists", "pra"):
                            lb = raw.get((d, pid, mk))
                            mr = main_rung(lb) if lb else None
                            if not mr:
                                continue
                            line, ov, un = mr
                            act = r["pts"] + r["reb"] + r["ast"] if mk == "pra" else r[{"points": "pts", "rebounds": "reb", "assists": "ast"}[mk]]
                            rows.append({"season": s, "date": d, "pid": pid, "market": mk, "line": line, "actual": act,
                                         "u_over": 0.0 if act == line else (ov - 1 if act > line else -1.0),
                                         "u_under": 0.0 if act == line else (un - 1 if act < line else -1.0),
                                         "mpg": ps["min"] / ps["n"], "pf36": 36 * ps["pf"] / ps["min"] if ps["min"] else 0.0,
                                         "group": groups.get(pid), "b2b": b2b, "opp_fta": opp_fta, "opp_miss": opp_miss,
                                         "rc": ps["rc"] / ps["n_trk"] if ps["n_trk"] else None, "returning": pid in returning,
                                         "pred_margin": pm, "pred_total": ptot})
            for gid, box in day.items():                  # the date's games join the totals
                teams = sorted({r["team"] for r in box.values()})
                if len(teams) != 2:
                    continue
                tot = {tm: {k: sum(r[k] for r in box.values() if r["team"] == tm) for k in ("pts", "fga", "fgm", "fta")} for tm in teams}
                for tm in teams:
                    opp = teams[1] if tm == teams[0] else teams[0]
                    st = T[tm]
                    st["n"] += 1
                    st["for"] += tot[tm]["pts"]
                    st["against"] += tot[opp]["pts"]
                    st["fta"] += tot[tm]["fta"]
                    st["miss"] += tot[tm]["fga"] - tot[tm]["fgm"]
                    st["dates"].append(d)
                    st["box"].append({p: r["min"] for p, r in box.items() if r["team"] == tm and r["min"]})
                for pid, r in box.items():
                    if r["min"]:
                        ps = P[(s, pid)]
                        ps["n"] += 1
                        ps["min"] += r["min"]
                        ps["pf"] += r["pf"]
                        if trk and d in tracked:
                            ps["rc"] += trk.get((d, pid), 0.0)
                            ps["n_trk"] += 1
    return rows


def _returning(history, tonight):
    """Idea 4: teammates B whose minutes rose >= 4 while a rotation player X (>= 20 min over >= 3 games) missed >= 2
    straight games, and X plays tonight. history: the team's games so far, [{pid: minutes}], oldest first."""
    out = set()
    for x in tonight:
        played = [b for b in history if x in b]
        if len(played) < 3 or sum(b[x] for b in played) / len(played) < 20:
            continue
        streak = []
        for b in reversed(history):
            if x in b:
                break
            streak.append(b)
        if len(streak) < 2:
            continue
        with_x = [b for b in history if x in b]
        for p in tonight - {x}:
            wo = [b[p] for b in streak if p in b]
            wi = [b[p] for b in with_x if p in b]
            if wo and wi and sum(wo) / len(wo) - sum(wi) / len(wi) >= 4:
                out.add(p)
    return out


def summ(rs, side):
    if not rs:
        return {"n": 0}
    k = "u_" + side
    np_ = [r for r in rs if r["actual"] != r["line"]]
    win = (lambda r: r["actual"] > r["line"]) if side == "over" else (lambda r: r["actual"] < r["line"])
    return {"n": len(rs), "hit": round(float(np.mean([win(r) for r in np_])), 4) if np_ else None,
            "roi": round(float(np.mean([r[k] for r in rs])), 4)}


def evaluate(rows):
    fit = [r for r in rows if r["season"] == SEASONS[0]]
    ftas = [r["opp_fta"] for r in fit if r["opp_fta"] is not None]
    misses = [r["opp_miss"] for r in fit if r["opp_miss"] is not None]
    tots = [r["pred_total"] for r in fit if r["pred_total"] is not None]
    cut = {"opp_fta_p67": float(np.percentile(ftas, 67)), "opp_miss_median": float(np.median(misses)),
           "opp_miss_top_tercile": float(np.percentile(misses, 200 / 3)), "pred_total_top_quintile": float(np.percentile(tots, 80))}
    big = lambda r: r["group"] in ("F", "C")
    ideas = {
        "1a b2b: unders, 32+ min": ("under", lambda r: r["mpg"] >= 32 and r["b2b"], lambda r: r["mpg"] >= 32 and not r["b2b"]),
        "1b b2b: overs, 15-24 min": ("over", lambda r: 15 <= r["mpg"] < 24 and r["b2b"], lambda r: 15 <= r["mpg"] < 24 and not r["b2b"]),
        "2 foul-prone bigs: unders": ("under", lambda r: big(r) and r["market"] in ("points", "rebounds") and r["pf36"] >= 4.5
                                      and r["opp_fta"] is not None and r["opp_fta"] > cut["opp_fta_p67"],
                                      lambda r: big(r) and r["market"] in ("points", "rebounds")),
        "3a RC 2x + opponent misses: overs": ("over", lambda r: r["market"] == "rebounds" and r["rc"] is not None and r["rc"] >= 2 * r["line"]
                                              and r["opp_miss"] is not None and r["opp_miss"] > cut["opp_miss_median"],
                                              lambda r: r["market"] == "rebounds" and r["rc"] is not None and r["rc"] >= 2 * r["line"]),
        "3b opponent misses top tercile: overs": ("over", lambda r: r["market"] == "rebounds" and r["opp_miss"] is not None
                                                  and r["opp_miss"] > cut["opp_miss_top_tercile"], lambda r: r["market"] == "rebounds"),
        "4 teammate returns: unders": ("under", lambda r: r["returning"], lambda r: True),
        "6a expected blowout: unders, 30+ min": ("under", lambda r: r["market"] in ("points", "pra") and r["mpg"] >= 30 and r["pred_margin"] is not None
                                                 and abs(r["pred_margin"]) >= 10,
                                                 lambda r: r["market"] in ("points", "pra") and r["mpg"] >= 30 and r["pred_margin"] is not None
                                                 and abs(r["pred_margin"]) < 10),
        "6b high expected total: overs, 28+ min": ("over", lambda r: r["market"] == "points" and r["mpg"] >= 28 and r["pred_total"] is not None
                                                   and r["pred_total"] > cut["pred_total_top_quintile"],
                                                   lambda r: r["market"] == "points" and r["mpg"] >= 28 and r["pred_total"] is not None
                                                   and r["pred_total"] <= cut["pred_total_top_quintile"])}
    res = {"cuts (2023-24)": {k: round(v, 3) for k, v in cut.items()}, "ideas": {}}
    for name, (side, sel, base) in ideas.items():
        out = {s: {"idea": summ([r for r in rows if r["season"] == s and sel(r)], side),
                   "baseline": summ([r for r in rows if r["season"] == s and base(r)], side)} for s in SEASONS}
        out["side"] = side
        out["passes"] = all(out[s]["idea"].get("n") and out[s]["idea"]["roi"] > 0 and out[s]["idea"]["roi"] > out[s]["baseline"]["roi"]
                            for s in SEASONS)
        res["ideas"][name] = out
    return res


# ── amendment 1: the forward decisions (shared by the side-by-side and the live pinger) ──────────────────────────
FOUL_PF36, FOUL_OPP_FTA, RESTRICT_WORDS = 4.5, 23.5, ("minutes restriction", "minute restriction", "minutes limit", "limited minutes")


def return_bets(history, cleared, with_boards):
    """RETURN_UNDER: teammates (with a board) to fade when a rotation player who missed >= 2 straight games is cleared.
    history: the team's games this season, [{pid: minutes}], oldest first; cleared: absent players not listed out."""
    return {b for b in _returning(history, set(with_boards) | set(cleared)) if b in with_boards}


class FoulData:
    """FOUL_BIG's inputs this season before a date: personal fouls per 36 by player, FTA drawn per game by team."""

    def __init__(self, matchup_db, season):
        m = sqlite3.connect(f"file:{matchup_db}?mode=ro", uri=True) if Path(matchup_db).exists() else None
        self.player, self.team = defaultdict(list), defaultdict(lambda: defaultdict(float))   # pid -> [(date, min, pf)]
        if m is not None:
            cols = {r[1] for r in m.execute("PRAGMA table_info(player_games)")}
            pf = "p.pf" if "pf" in cols else "NULL"
            for d, gid, team, pid, mn, f, fta in m.execute(
                    f"SELECT gm.date, p.gid, p.team, p.pid, p.min, {pf}, p.fta FROM player_games p JOIN games gm ON gm.gid = p.gid "
                    f"WHERE gm.season = ?", (season,)):
                if mn:
                    self.player[pid].append((d, mn, f))
                self.team[team][(d, gid)] += fta or 0

    def pf36(self, pid, date):
        g = [(mn, f) for d, mn, f in self.player.get(pid, ()) if d < date]
        if len(g) < 5 or any(f is None for _m, f in g):
            return None
        mins = sum(mn for mn, _f in g)
        return 36 * sum(f for _m, f in g) / mins if mins else None

    def fta_per_game(self, team, date):
        g = [v for (d, _g), v in self.team.get(team, {}).items() if d < date]
        return sum(g) / len(g) if len(g) >= 10 else None


def foul_bet(fd, group, pid, opp, date):
    """FOUL_BIG: an F/C fouling >= 4.5 per 36 against a team drawing > 23.5 FTA a game."""
    if group not in ("F", "C") or not opp:
        return False
    pf, fta = fd.pf36(pid, date), fd.fta_per_game(opp, date)
    return pf is not None and fta is not None and pf >= FOUL_PF36 and fta > FOUL_OPP_FTA


def restricted(text):
    t = (text or "").lower()
    return any(w in t for w in RESTRICT_WORDS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gamelogs", required=True)
    ap.add_argument("--odds", required=True)
    ap.add_argument("--matchup", required=True)
    ap.add_argument("--tracking")
    ap.add_argument("--json")
    a = ap.parse_args()
    res = evaluate(build(a.gamelogs, a.odds, a.matchup, a.tracking))
    print(json.dumps(res, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
