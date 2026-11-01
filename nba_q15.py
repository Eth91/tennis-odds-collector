#!/usr/bin/env python3
"""NBA_Q15 (NBA_Q15_PREREG.md): the prop dataset, the models and the backtest.

The dataset: every main-line player prop at FanDuel, DraftKings, BetMGM and Caesars about 30 minutes before tip
(2023 playoffs to 2025 playoffs), joined to the box score, with features from games before tonight only.

    python3 nba_q15.py build            # the dataset -> CACHE
    python3 nba_q15.py baseline         # experiment 1: the market's calibration and blanket overs/unders
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ODDS = HERE / "basketball_nba_odds_hist.sqlite"
GAMELOGS = HERE / "nba_gamelogs.sqlite"
POST = HERE / "nba_postseason.sqlite"
CACHE = Path(os.environ.get("NBA_Q15_CACHE", HERE / ".q15cache"))     # the dataset and projections (not in git)

TEAM = {"Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN", "Charlotte Hornets": "CHA",
        "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN",
        "Detroit Pistons": "DET", "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
        "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM", "Miami Heat": "MIA",
        "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP", "New York Knicks": "NYK",
        "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX",
        "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR",
        "Utah Jazz": "UTA", "Washington Wizards": "WAS"}
MARKETS = {"player_points": "points", "player_rebounds": "rebounds", "player_assists": "assists",
           "player_threes": "threes", "player_points_rebounds": "pts_reb", "player_points_assists": "pts_ast",
           "player_rebounds_assists": "reb_ast", "player_points_rebounds_assists": "pra"}
PARTS = {"points": ("pts",), "rebounds": ("reb",), "assists": ("ast",), "threes": ("fg3m",), "pts_reb": ("pts", "reb"),
         "pts_ast": ("pts", "ast"), "reb_ast": ("reb", "ast"), "pra": ("pts", "reb", "ast")}
BOOKS = {"fanduel": "fd", "draftkings": "dk", "betmgm": "mgm", "williamhill_us": "czr"}
RATE_K = 300.0              # minutes of last season's rate behind this season's (shrinkage)
ROT_MIN = 15.0              # a rotation teammate: 15+ minutes a game over his last 10


def split_of(date, post):
    """TRAIN 2023-24 regular season, VALIDATE 2024-25 regular season, TEST A the postseasons (NBA_Q15_PREREG.md)."""
    if post:
        return "TEST_A"
    if "2023-10-01" <= date <= "2024-04-30":
        return "TRAIN"
    if "2024-10-01" <= date <= "2025-04-30":
        return "VALIDATE"
    return "OTHER"                                          # the NBA Cup finals and anything stray


# ── box scores ──────────────────────────────────────────────────────────────────────────────────────────────────────
def load_box():
    cols = "season, game_id, date, team, player_id AS pid, player, min, pts, reb, ast, fg3m, fga, fg3a, fta, tov, oreb"
    g = sqlite3.connect(f"file:{GAMELOGS}?mode=ro", uri=True)
    rs = pd.read_sql(f"SELECT {cols} FROM logs_full", g)
    rs["post"] = 0
    p = sqlite3.connect(f"file:{POST}?immutable=1", uri=True)
    po = pd.read_sql(f"SELECT {cols} FROM logs_post", p)
    po["post"] = 1
    b = pd.concat([rs, po], ignore_index=True)
    b["min"] = b["min"].fillna(0.0)
    for c in ("pts", "reb", "ast", "fg3m", "fga", "fg3a", "fta", "tov", "oreb"):
        b[c] = b[c].fillna(0.0)
    b = b[b["min"] > 0].copy()
    for m, ps in PARTS.items():
        b["s_" + m] = sum(b[x] for x in ps)
    b = b.sort_values(["date", "game_id", "team", "pid"]).reset_index(drop=True)
    teams = b.groupby("game_id")["team"].unique()
    opp = {g_: dict(zip(ts, ts[::-1])) for g_, ts in teams.items() if len(ts) == 2}
    b["opp"] = [opp.get(g_, {}).get(t) for g_, t in zip(b["game_id"], b["team"])]
    return b


def player_features(b):
    """Per (pid, date): his numbers over games before tonight."""
    b = b.sort_values(["pid", "date", "game_id"]).copy()
    g = b.groupby("pid", sort=False)
    out = b[["pid", "date", "game_id", "team", "opp", "season", "post", "min"] + ["s_" + m for m in PARTS]].copy()
    sh = lambda s: s.shift(1)
    for k in (3, 5, 10):
        out[f"min_l{k}"] = g["min"].transform(lambda s: s.shift(1).rolling(k, min_periods=1).mean())
    out["prev_date"] = g["date"].shift(1)
    out["gp_career"] = g.cumcount()
    # this season so far (regular season and playoffs together), before tonight
    gs = b.groupby(["pid", "season"], sort=False)
    out["gp_season"] = gs.cumcount()
    out["min_season_sum"] = gs["min"].transform(lambda s: s.shift(1).cumsum()).fillna(0.0)
    for m in PARTS:
        c = "s_" + m
        out[f"{m}_l5"] = g[c].transform(lambda s: s.shift(1).rolling(5, min_periods=1).mean())
        out[f"{m}_l10"] = g[c].transform(lambda s: s.shift(1).rolling(10, min_periods=1).mean())
        out[f"{m}_med10"] = g[c].transform(lambda s: s.shift(1).rolling(10, min_periods=3).median())
        out[f"{m}_sd10"] = g[c].transform(lambda s: s.shift(1).rolling(10, min_periods=3).std())
        out[f"{m}_season_sum"] = gs[c].transform(lambda s: s.shift(1).cumsum()).fillna(0.0)
    # last season's totals and rates
    tot = b.groupby(["pid", "season"]).agg(**{"lmin": ("min", "sum"), "lgp": ("min", "size")},
                                             **{f"l_{m}": ("s_" + m, "sum") for m in PARTS}).reset_index()
    order = sorted(b["season"].unique())
    nxt = {s: order[i + 1] for i, s in enumerate(order[:-1])}
    tot["season"] = tot["season"].map(nxt)
    out = out.merge(tot.dropna(subset=["season"]), on=["pid", "season"], how="left")
    # the league's per-minute rate over every game before the date (the prior for a player with no last season)
    cum = b.groupby("date")[["min"] + ["s_" + m for m in PARTS]].sum().sort_index().cumsum().shift(1).bfill()
    for m in PARTS:
        league = out["date"].map(cum["s_" + m] / cum["min"])
        prev_rate = (out[f"l_{m}"] / out["lmin"]).where(out["lmin"] > 0, league)
        out[f"{m}_rate"] = (out[f"{m}_season_sum"] + RATE_K * prev_rate) / (out["min_season_sum"] + RATE_K)
        out[f"{m}_season_avg"] = (out[f"{m}_season_sum"] / out["gp_season"]).where(out["gp_season"] > 0)
    out["min_season_avg"] = (out["min_season_sum"] / out["gp_season"]).where(out["gp_season"] > 0)
    out["last_mpg"] = out["lmin"] / out["lgp"]
    out["rest"] = (pd.to_datetime(out["date"]) - pd.to_datetime(out["prev_date"])).dt.days
    return out


def team_totals(b):
    """Per (team, game): the possession parts and each stat, summed over the box."""
    return b.groupby(["game_id", "date", "team", "opp", "post"]).agg(
        fga=("fga", "sum"), fta=("fta", "sum"), tov=("tov", "sum"), oreb=("oreb", "sum"),
        **{"s_" + m: ("s_" + m, "sum") for m in PARTS}).reset_index()


def team_league(t):
    """The normalizers: the mean team-game possessions and each stat allowed (constants; frozen for the live model)."""
    t = with_allowed(t)
    return {c: float(t[c].mean()) for c in ["poss"] + ["a_" + m for m in PARTS]}


def with_allowed(t):
    t = t.copy()
    t["poss"] = t["fga"] + 0.44 * t["fta"] + t["tov"] - t["oreb"]
    allowed = t[["game_id", "team"] + ["s_" + m for m in PARTS] + ["poss"]].rename(
        columns={"team": "opp", **{"s_" + m: "a_" + m for m in PARTS}, "poss": "a_poss"})
    return t.merge(allowed, on=["game_id", "opp"], how="left")


def team_features(b, league=None, t=None):
    """Per (team, game): pace and what the opponent allows, over games before tonight (last 20). `t` (team_totals) and
    `league` (team_league) may be given: the live model passes its own box's totals and the training normalizers."""
    t = team_totals(b) if t is None else t
    league = league or team_league(t)
    t = with_allowed(t).sort_values(["team", "date", "game_id"])
    g = t.groupby("team", sort=False)
    roll = lambda c: g[c].transform(lambda s: s.shift(1).rolling(20, min_periods=5).mean())
    f = t[["game_id", "date", "team", "opp"]].copy()
    f["pace"] = roll("poss")
    for m in PARTS:
        f["allow_" + m] = roll("a_" + m)
    f["pace_r"] = f["pace"] / league["poss"]
    for m in PARTS:
        f["allow_r_" + m] = f["allow_" + m] / league["a_" + m]
    # opponent's pace and what tonight's opponent allows
    o = f[["game_id", "team", "pace_r"] + ["allow_r_" + m for m in PARTS]].rename(
        columns={"team": "opp", "pace_r": "opp_pace_r", **{"allow_r_" + m: "opp_allow_r_" + m for m in PARTS}})
    f = f.merge(o, on=["game_id", "opp"], how="left")
    return f[["game_id", "team", "pace_r", "opp_pace_r"] + ["opp_allow_r_" + m for m in PARTS]]


def vacated(b, pf):
    """Per (team, game): minutes a game (last 10) of rotation teammates who played one of the team's last 3 games
    but not tonight, and his own team games missed in a row before tonight. Tonight's absences come from the box
    score (the pre-registered hindsight: the inactive list is known by tip - 30)."""
    l10 = pf.set_index(["pid", "game_id"])["min_l10"].to_dict()
    tg = b.groupby(["team", "date", "game_id"])["pid"].apply(set).reset_index().sort_values(["team", "date", "game_id"])
    vac, missed = {}, {}
    for team, rows in tg.groupby("team", sort=False):
        hist = []                                          # [(game_id, set of pids)]
        last_l10 = {}                                      # pid -> his min_l10 at his last game for the team
        for _, r in rows.iterrows():
            recent = set().union(*[s for _g, s in hist[-3:]]) if hist else set()
            out = [p for p in recent - r["pid"] if last_l10.get(p, 0) >= ROT_MIN]
            vac[(team, r["game_id"])] = (sum(last_l10[p] for p in out), len(out))
            for p in r["pid"]:
                n = 0
                for _g, s in reversed(hist):
                    if p in s:
                        break
                    n += 1
                missed[(p, r["game_id"])] = n if hist and any(p in s for _g, s in hist) else -1
                v = l10.get((p, r["game_id"]))
                # his last-10 average including tonight, for the next game's check
                last_l10[p] = v if v == v and v is not None else 0.0
            hist.append((r["game_id"], r["pid"]))
    return vac, missed


# ── lines ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def load_lines(name2pid):
    o = sqlite3.connect(f"file:{ODDS}?immutable=1", uri=True)
    q = ("SELECT game_date, event_id, home_team, away_team, commence_time, book, market, player, side, line, price "
         "FROM props WHERE snap_kind = 'tip' AND book IN (%s) AND market IN (%s) AND price IS NOT NULL AND line IS NOT NULL"
         % (",".join("?" * len(BOOKS)), ",".join("?" * len(MARKETS))))
    raw = defaultdict(lambda: defaultdict(dict))          # key -> book -> line -> [over, under]
    meta = {}
    import nba_margin_refit as MR
    for d, ev, home, away, ct, book, mk, pl, side, line, price in o.execute(q, tuple(BOOKS) + tuple(MARKETS)):
        pid = name2pid.get(MR.norm(pl))
        if pid is None:
            continue
        k = (d, pid, MARKETS[mk])
        raw[k][BOOKS[book]].setdefault(float(line), [None, None])[0 if side == "Over" or side == "over" else 1] = float(price)
        meta[k] = (ev, TEAM.get(home), TEAM.get(away), ct)
    rows = []
    for k, bks in raw.items():
        per = {}
        for bk, lines in bks.items():
            two = [(ln, v) for ln, v in lines.items() if v[0] and v[1]]
            if two:                                         # a book's main line: its over nearest even money
                ln, v = min(two, key=lambda x: abs(x[1][0] - 2.0))
                per[bk] = (ln, v[0], v[1])
        if not per:
            continue
        cnt = defaultdict(int)
        for ln, _o, _u in per.values():
            cnt[ln] += 1
        top = max(cnt.values())
        cands = sorted(ln for ln, n in cnt.items() if n == top)
        line_c = per["fd"][0] if "fd" in per and per["fd"][0] in cands else cands[len(cands) // 2]
        at = {bk: v for bk, v in per.items() if v[0] == line_c}
        nv = [(1 / ov) / (1 / ov + 1 / un) for _ln, ov, un in at.values()]
        hold = [1 / ov + 1 / un - 1 for _ln, ov, un in at.values()]
        ev, home, away, ct = meta[k]
        r = {"date": k[0], "pid": k[1], "market": k[2], "event": ev, "home": home, "away": away, "commence": ct,
             "line": line_c, "n_books": len(at), "n_books_any": len(per), "p_mkt": float(np.mean(nv)),
             "hold": float(np.mean(hold)), "disp": max(v[0] for v in per.values()) - min(v[0] for v in per.values())}
        for bk in BOOKS.values():
            v = per.get(bk)
            r[bk + "_line"], r[bk + "_o"], r[bk + "_u"] = (v if v else (None, None, None))
        rows.append(r)
    return pd.DataFrame(rows)


def build():
    CACHE.mkdir(parents=True, exist_ok=True)
    b = load_box()
    import nba_margin_refit as MR
    names = b.groupby("pid")["player"].last()
    seen = defaultdict(set)
    for pid, nm in names.items():
        seen[MR.norm(nm)].add(pid)
    name2pid = {n: next(iter(p)) for n, p in seen.items() if len(p) == 1}
    L = load_lines(name2pid)
    pf = player_features(b)
    tf = team_features(b)
    vac, missed = vacated(b, pf)
    pf["vac_min"] = [vac.get((t, g), (0, 0))[0] for t, g in zip(pf["team"], pf["game_id"])]
    pf["vac_n"] = [vac.get((t, g), (0, 0))[1] for t, g in zip(pf["team"], pf["game_id"])]
    pf["missed"] = [missed.get((p, g), -1) for p, g in zip(pf["pid"], pf["game_id"])]
    pf = pf.merge(tf, on=["game_id", "team"], how="left")
    d = L.merge(pf, on=["date", "pid"], how="left")
    d["played"] = d["game_id"].notna()
    d["actual"] = [r["s_" + m] if p else np.nan for r, m, p in zip(d.to_dict("records"), d["market"], d["played"])]
    d["post"] = d["post"].fillna(0).astype(int)
    # a void prop (he did not play) has no box row; its postseason flag comes from the date
    post_dates = set(b.loc[b["post"] == 1, "date"])
    d.loc[~d["played"], "post"] = d.loc[~d["played"], "date"].isin(post_dates).astype(int)
    d["split"] = [split_of(dt_, p) for dt_, p in zip(d["date"], d["post"])]
    d["team_ok"] = [(t in (h, a)) if isinstance(t, str) else False for t, h, a in zip(d["team"], d["home"], d["away"])]
    d["home_flag"] = (d["team"] == d["home"]).astype(int)
    keep = [c for c in d.columns if not c.startswith("s_")]
    d = d[keep]
    d.to_pickle(CACHE / "dataset.pkl")
    print(f"dataset: {len(d)} props, {d['played'].sum()} played, team ok {d['team_ok'].mean():.3f}")
    print(d.groupby("split").size().to_dict())
    return d


def load():
    return pd.read_pickle(CACHE / "dataset.pkl")


# ── grading ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def price_at(d, side, books):
    """The best price for the side among the books posting the consensus line, and which book."""
    best, who = np.full(len(d), np.nan), np.array([None] * len(d), dtype=object)
    for bk in books:
        ok = (d[bk + "_line"] == d["line"]).to_numpy()
        p = d[bk + ("_o" if side == "over" else "_u")].to_numpy(dtype=float)
        better = ok & ~np.isnan(p) & (np.isnan(best) | (p > best))
        best[better], who[better] = p[better], bk
    return best, who


def grade(d, side, price):
    a, ln = d["actual"].to_numpy(float), d["line"].to_numpy(float)
    win = a > ln if side == "over" else a < ln
    push = a == ln
    return np.where(push, 0.0, np.where(win, price - 1, -1.0)), np.where(push, np.nan, win.astype(float))


def summary(u, win, price, keys, boot=2000, seed=7):
    """ROI, bets, win rate against break-even, units, max drawdown, clustered bootstrap intervals."""
    u, win, price = np.asarray(u, float), np.asarray(win, float), np.asarray(price, float)
    n = len(u)
    if not n:
        return {"n": 0}
    cum = np.cumsum(u)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], cum]))[1:] - cum)) if n else 0.0
    dec = ~np.isnan(win)
    out = {"n": n, "roi": round(float(u.mean()), 4), "units": round(float(u.sum()), 1),
           "win": round(float(np.nanmean(win)), 4) if dec.any() else None,
           "breakeven": round(float(np.mean(1 / price[dec])), 4) if dec.any() else None,
           "max_dd": round(dd, 1)}
    if boot:
        cl = pd.Series(u).groupby(np.asarray(keys)).agg(["sum", "size"]).to_numpy()
        rng = np.random.default_rng(seed)
        idx = rng.integers(0, len(cl), size=(boot, len(cl)))
        r = cl[idx, 0].sum(1) / cl[idx, 1].sum(1)
        out["ci90"] = [round(float(np.quantile(r, .05)), 4), round(float(np.quantile(r, .95)), 4)]
        out["ci95"] = [round(float(np.quantile(r, .025)), 4), round(float(np.quantile(r, .975)), 4)]
    return out


def logloss(p, y):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(p, y):
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


# ── experiment 1: the market ────────────────────────────────────────────────────────────────────────────────────────
def baseline(d):
    d = d[d["played"] & d["team_ok"]].copy()
    d = d[d["actual"] != d["line"]]
    d["y"] = (d["actual"] > d["line"]).astype(float)
    res = {}
    for sp in ("TRAIN", "VALIDATE"):
        s = d[d["split"] == sp]
        r = {"n": len(s), "over_rate": round(s["y"].mean(), 4), "p_mkt": round(s["p_mkt"].mean(), 4),
             "logloss_mkt": round(logloss(s["p_mkt"], s["y"]), 5), "brier_mkt": round(brier(s["p_mkt"], s["y"]), 5),
             "logloss_coin": round(logloss(np.full(len(s), s["y"].mean()), s["y"]), 5)}
        for side in ("over", "under"):
            for name, books in (("fd_dk", ("fd", "dk")), ("best4", ("fd", "dk", "mgm", "czr"))):
                pr, _ = price_at(s, side, books)
                ok = ~np.isnan(pr)
                u, w = grade(s[ok], side, pr[ok])
                r[f"{side}_{name}"] = summary(u, w, pr[ok], s[ok]["date"] + s[ok]["pid"].astype(str), boot=0)
        r["by_market"] = {m: {"n": int(len(g)), "over_rate": round(g["y"].mean(), 4), "p_mkt": round(g["p_mkt"].mean(), 4)}
                          for m, g in s.groupby("market")}
        bins = pd.cut(s["p_mkt"], [0, .35, .45, .5, .55, .65, 1])
        r["calibration"] = {str(k): {"n": int(len(g)), "p": round(g["p_mkt"].mean(), 4), "over": round(g["y"].mean(), 4)}
                            for k, g in s.groupby(bins, observed=True)}
        res[sp] = r
    return res


# ── features and walk-forward models (experiments 2+) ───────────────────────────────────────────────────────────────
MKTS = tuple(PARTS)


def logit(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def features(d):
    """The model's inputs, all from before tonight (and the tip − 30 prices). NaN where unknown."""
    f = pd.DataFrame(index=d.index)
    f["logit_p"] = logit(d["p_mkt"])
    ln = d["line"].astype(float)
    pick = lambda suffix: np.select([d["market"] == m for m in MKTS], [d[f"{m}_{suffix}"] for m in MKTS], np.nan)
    rate, l5, l10, med10, sd10, savg = (pick(x) for x in ("rate", "l5", "l10", "med10", "sd10", "season_avg"))
    allow = np.select([d["market"] == m for m in MKTS], [d[f"opp_allow_r_{m}"] for m in MKTS], np.nan)
    minp = 0.5 * d["min_l5"] + 0.5 * d["min_l10"]
    proj = minp * rate
    r = lambda x: np.log((np.asarray(x, float) + 0.5) / (ln + 0.5))
    f["r_proj"] = r(proj)
    f["r_l5"], f["r_l10"], f["r_med10"], f["r_savg"] = r(l5), r(l10), r(med10), r(savg)
    f["cv10"] = sd10 / (l10 + 1.0)
    f["log_line"] = np.log1p(ln)
    f["min_trend"] = d["min_l3"] - d["min_l10"]
    f["min_vs_season"] = d["min_l5"] - d["min_season_avg"]
    f["min_l10"] = d["min_l10"]
    f["gp_season"] = np.log1p(d["gp_season"])
    f["rest"] = d["rest"].clip(0, 6)
    f["b2b"] = (d["rest"] == 1).astype(float)
    f["home"] = d["home_flag"].astype(float)
    f["pace"] = d["pace_r"] + d["opp_pace_r"] - 2
    f["opp_allow"] = allow - 1
    f["vac_min"] = d["vac_min"] / 48.0
    f["vac_n"] = d["vac_n"]
    f["returning"] = (d["missed"] >= 1).astype(float)
    f["disp"] = d["disp"]
    f["n_books"] = d["n_books"]
    f["hold"] = d["hold"]
    fdnv = (1 / d["fd_o"]) / (1 / d["fd_o"] + 1 / d["fd_u"])
    f["fd_vs_mkt"] = (fdnv - d["p_mkt"]).where(d["fd_line"] == d["line"])
    for m in MKTS:
        f["m_" + m] = (d["market"] == m).astype(float)
    return f


def frame(d):
    """Played props on the right teams with a decided result, features and labels, in date order."""
    d = d[d["played"] & d["team_ok"] & d["split"].isin(["TRAIN", "VALIDATE", "TEST_A"])].copy()
    d = d.sort_values(["date", "event", "pid", "market"]).reset_index(drop=True)
    d["y"] = np.where(d["actual"] > d["line"], 1.0, np.where(d["actual"] < d["line"], 0.0, np.nan))
    d["month"] = d["date"].str[:7]
    return d, features(d)


def fit_logistic(X, y, C=0.05):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer
    m = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=C, max_iter=2000))
    m.fit(X, y)
    return lambda Z: m.predict_proba(Z)[:, 1]


def fit_lgbm(X, y, params=None, rounds=400):
    import lightgbm as lgb
    P = dict(objective="binary", learning_rate=0.02, num_leaves=15, min_data_in_leaf=800, lambda_l2=20.0,
             feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1, verbose=-1, seed=7)
    P.update(params or {})
    cols = [c for c in X.columns if c != "logit_p"]
    ds = lgb.Dataset(X[cols], y, init_score=X["logit_p"].to_numpy())
    b = lgb.train(P, ds, num_boost_round=rounds)
    return lambda Z: 1 / (1 + np.exp(-(Z["logit_p"].to_numpy() + b.predict(Z[cols], raw_score=True))))


def walk_forward(d, X, fit, start="2023-12", until="2025-04"):
    """Each month predicted by a model fit on every decided prop before it (TRAIN and VALIDATE only)."""
    p = pd.Series(np.nan, index=d.index)
    months = sorted(m for m in d.loc[d["split"].isin(["TRAIN", "VALIDATE"]), "month"].unique() if start <= m <= until)
    for m in months:
        tr = (d["month"] < m) & d["split"].isin(["TRAIN", "VALIDATE"]) & d["y"].notna()
        te = (d["month"] == m) & d["split"].isin(["TRAIN", "VALIDATE"])
        f = fit(X[tr], d.loc[tr, "y"])
        p[te] = f(X[te])
    return p


def bets(d, p, tau, books=("fd", "dk"), sides=("over", "under")):
    """Every prop where the model's EV at the best price (books at the consensus line) is at least tau: the side
    with the higher EV."""
    rows = []
    po, _ = price_at(d, "over", books)
    pu, _ = price_at(d, "under", books)
    ev_o, ev_u = p * po - 1, (1 - p) * pu - 1
    for side, ev, pr in (("over", ev_o, po), ("under", ev_u, pu)):
        if side not in sides:
            continue
        other = ev_u if side == "over" else ev_o
        ok = (ev >= tau) & ~np.isnan(pr) & ~np.isnan(p) & ((ev >= other) | np.isnan(other))
        s = d[ok].copy()
        s["side"], s["price"], s["ev"], s["p_side"] = side, pr[ok], ev[ok], (p[ok] if side == "over" else 1 - p[ok])
        u, w = grade(s, side, s["price"].to_numpy())
        s["u"], s["win"] = u, w
        rows.append(s)
    return pd.concat(rows) if rows else pd.DataFrame()


def report(b, by=("split",)):
    out = {}
    for k, g in b.groupby(list(by)):
        out[str(k)] = summary(g["u"], g["win"], g["price"], g["date"] + g["pid"].astype(str))
    return out


def scores(d, p, mask):
    ok = mask & d["y"].notna() & p.notna()
    return {"n": int(ok.sum()), "ll_model": round(logloss(p[ok], d.loc[ok, "y"]), 5),
            "ll_mkt": round(logloss(d.loc[ok, "p_mkt"], d.loc[ok, "y"]), 5),
            "brier_model": round(brier(p[ok], d.loc[ok, "y"]), 5), "brier_mkt": round(brier(d.loc[ok, "p_mkt"], d.loc[ok, "y"]), 5)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("build", "baseline"))
    a = ap.parse_args()
    if a.cmd == "build":
        build()
    elif a.cmd == "baseline":
        print(json.dumps(baseline(load()), indent=1, default=str))


if __name__ == "__main__":
    main()
