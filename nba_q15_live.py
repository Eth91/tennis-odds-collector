#!/usr/bin/env python3
"""NBA_Q15 TEST B: the frozen Q15_LR model (nba_q15_lr_model) on tonight's props. Shadow only: nothing is bet or pinged.

Tonight's inputs are what is known at tip - 30:
- the box scores before tonight;
- the injury report (Out / Doubtful) in place of the box score's "did not play";
- the engine's ROLE1 v3 projection from that report;
- FanDuel's and DraftKings' main lines.

The features come from nba_q15's own code. Each player who may play tonight gets a placeholder box row. Every feature
is shifted one game, so a placeholder's features are exactly "everything before tonight" (test_nba_q15 proves tonight's
box cannot change them). The team normalizers are the training ones, frozen in the model.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

import nba_q15 as Q
import nba_q15_model as QM
from nba_q15_lr_model import MODEL

BOX_COLS = ("pts", "reb", "ast", "fg3m", "fga", "fg3a", "fta", "tov", "oreb")


def box_from_matchup(matchup_db, seasons, before):
    """(player rows as nba_q15.load_box gives them, team totals as nba_q15.team_totals gives them) for the seasons'
    games before the date, from nba_matchup. Team possessions come from team_games (player_games has no oreb).
    (None, None) when the store lacks those tables."""
    if not Path(matchup_db).exists():
        return None, None
    c = sqlite3.connect(f"file:{matchup_db}?mode=ro", uri=True)
    if not {"games", "player_games", "team_games"} <= {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}:
        c.close()
        return None, None
    marks = ",".join("?" * len(seasons))
    b = pd.read_sql(f"SELECT g.season, p.gid AS game_id, g.date, p.team, p.pid, p.min, p.pts, p.reb, p.ast, p.fg3m, p.fga, "
                    f"p.fg3a, p.fta, p.tov, g.home, g.away FROM player_games p JOIN games g ON g.gid = p.gid "
                    f"WHERE g.season IN ({marks}) AND g.date < ?", c, params=[*seasons, before])
    tg = pd.read_sql(f"SELECT t.gid AS game_id, t.team, t.opp, t.fga, t.fta, t.oreb, t.tov FROM team_games t "
                     f"JOIN games g ON g.gid = t.gid WHERE g.season IN ({marks}) AND g.date < ?", c, params=[*seasons, before])
    c.close()
    b["min"] = b["min"].fillna(0.0)
    b["oreb"] = 0.0
    for col in BOX_COLS:
        b[col] = b[col].fillna(0.0)
    b = b[b["min"] > 0].copy()
    b["opp"] = np.where(b["team"] == b["home"], b["away"], b["home"])
    b["post"] = 0
    for m, ps in Q.PARTS.items():
        b["s_" + m] = sum(b[x] for x in ps)
    b = b.drop(columns=["home", "away"]).sort_values(["date", "game_id", "team", "pid"]).reset_index(drop=True)
    sums = b.groupby(["game_id", "date", "team", "opp", "post"])[["s_" + m for m in Q.PARTS]].sum().reset_index()
    t = sums.merge(tg[["game_id", "team", "fga", "fta", "oreb", "tov"]], on=["game_id", "team"], how="left")
    return b, t


class Night:
    """One date's features before any injury report: every candidate's own numbers and both teams' pace and allowed
    rates (none depend on who is out). frame() adds the teammates-out features for the players a report leaves."""

    def __init__(self, b, t, date, candidates, season):
        """candidates: [(pid, team, opp, gid)], everyone who might play tonight."""
        self.b, self.date, self.season = b, date, season
        ph = placeholders(candidates, date, season)
        self.pf = Q.player_features(pd.concat([b, ph], ignore_index=True))
        tt = ph.groupby(["game_id", "date", "team", "opp", "post"])[["s_" + m for m in Q.PARTS]].sum().reset_index()
        for c in ("fga", "fta", "oreb", "tov"):
            tt[c] = 0.0
        self.tf = Q.team_features(None, league=MODEL["team_league"], t=pd.concat([t, tt], ignore_index=True))
        self.tonight = self.pf[(self.pf["date"] == date).to_numpy()]

    def frame(self, players):
        """{pid: features} for players [(pid, team, opp, gid)] who may play tonight (not Out / Doubtful). The absent
        rotation players are whoever is missing from it, which is what nba_q15.vacated reads (from the teams' own rows,
        all it looks up)."""
        teams = {tm for _p, tm, _o, _g in players}
        bb = pd.concat([self.b[self.b["team"].isin(teams)], placeholders(players, self.date, self.season)], ignore_index=True)
        vac, missed = Q.vacated(bb, self.pf[self.pf["team"].isin(teams).to_numpy()])
        keys = {(int(p), tm) for p, tm, _o, _g in players}
        pf = self.tonight
        pf = pf[np.array([(int(p), tm) in keys for p, tm in zip(pf["pid"], pf["team"])], dtype=bool)].copy()
        pf["vac_min"] = [vac.get((tm, g), (0, 0))[0] for tm, g in zip(pf["team"], pf["game_id"])]
        pf["vac_n"] = [vac.get((tm, g), (0, 0))[1] for tm, g in zip(pf["team"], pf["game_id"])]
        pf["missed"] = [missed.get((p, g), -1) for p, g in zip(pf["pid"], pf["game_id"])]
        pf = pf.merge(self.tf, on=["game_id", "team"], how="left")
        return {int(r["pid"]): r for r in pf.to_dict("records")}


def placeholders(players, date, season):
    ph = pd.DataFrame([{"season": season, "game_id": g, "date": date, "team": tm, "pid": int(p), "min": 1.0, "opp": op, "post": 0,
                        **{c: 0.0 for c in BOX_COLS}} for p, tm, op, g in players],
                      columns=["season", "game_id", "date", "team", "pid", "min", "opp", "post", *BOX_COLS])
    for m in Q.PARTS:
        ph["s_" + m] = 0.0
    return ph


def player_frame(b, t, date, players, season):
    """{pid: features} for one night in one go (Night with the players as both the candidates and tonight's)."""
    return Night(b, t, date, players, season).frame(players)


def props_frame(pf, props, home, date):
    """One row per prop in nba_q15's dataset layout. props: [(pid, market, fd, dk)], fd / dk = (line, over, under) of
    the book's main rung or None; home: {gid: home team}."""
    rows = []
    for pid, mk, fd, dk in props:
        r = pf.get(int(pid))
        if r is None or not (fd or dk):
            continue
        row = dict(r, market=mk, date=date, actual=np.nan, split="TEST_B", home_flag=int(r["team"] == home.get(r["game_id"])),
                   disp=0.0, n_books=0, hold=np.nan, p_mkt=np.nan, mgm_line=np.nan, czr_line=np.nan, mgm_o=np.nan,
                   mgm_u=np.nan, czr_o=np.nan, czr_u=np.nan)
        for bk, v in (("fd", fd), ("dk", dk)):
            row[bk + "_line"], row[bk + "_o"], row[bk + "_u"] = v if v else (np.nan, np.nan, np.nan)
        row["line"] = row["fd_line"] if fd else row["dk_line"]
        rows.append(row)
    return pd.DataFrame(rows)


def score(d, proj):
    """(props with the model's p, ready for nba_q15_model.under_bets) for a props_frame. proj: {(date, pid, market):
    (projection, v3 minutes)}, the engine's, from tonight's report."""
    if d.empty:
        return d, pd.Series(dtype=float)
    X = Q.features(d)
    d, X = QM.with_engine(d, X, proj)
    d, X = QM.fd_dk_market(d, X)
    return d, pd.Series(QM.predict(MODEL, X), index=d.index)


def picks(d, p, tau):
    """[(pid, market, line, book, price, P(under), ev)]: Q15_LR's unders at EV >= tau, 12+ projected minutes, at the better of
    FanDuel and DraftKings at FanDuel's main line (else DraftKings')."""
    if d.empty:
        return []
    b = QM.under_bets(d, p, tau)
    if not len(b):
        return []
    _p, who = Q.price_at(b, "under", ("fd", "dk"))
    return [(int(r["pid"]), r["market"], float(r["line"]), w, float(r["price"]), float(r["p_side"]), float(r["ev"]))
            for r, w in zip(b.to_dict("records"), who)]
