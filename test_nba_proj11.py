"""proj-1.1 guards (NBA_PROJ11_PREREG.md): features use earlier dates only; F0's same-game proxy uses lineup
status and box-score presence only; the residual walk uses earlier months only; zero effect = proj-1.0."""
import copy

import numpy as np
import pytest

import nba_proj11 as P
import nba_proj11_feat as FT

DATES = [f"2024-01-{d:02d}" for d in range(1, 31)]
TEAMS = {"AAA": [1, 2, 3, 4, 5, 6], "BBB": [11, 12, 13, 14, 15, 16]}


def synth(skip=None):
    """Two teams playing each other every date; skip = {(date, pid)} missing from the box score."""
    rng = np.random.default_rng(3)
    rows = []
    for k, d in enumerate(DATES):
        for team, opp in (("AAA", "BBB"), ("BBB", "AAA")):
            for j, pid in enumerate(TEAMS[team]):
                if skip and (d, pid) in skip:
                    continue
                mn = [36, 34, 30, 26, 14, 10][j]
                rows.append({"date": d, "season": "2023-24", "gid": f"G{k}", "team": team, "opp": opp, "pid": pid,
                             "group": "GFCGFC"[j], "min": float(mn), "pts": float(rng.poisson(mn * .5)),
                             "reb": 3.0, "ast": 2.0, "fg3m": 1.0, "stl": 1.0, "blk": 0.0, "tov": 1.0,
                             "fga": mn * .4, "fta": 2.0, "home": int(team == "AAA")})
    return rows


def resp(cols, recs):
    return {"resultSets": [{"headers": cols, "rowSet": recs}]}


def synth_raw(rows, bump_from=None):
    """adv and usage per date, plus starters (the first five of each team)."""
    adv, usage, st = {}, {}, {}
    for d in DATES:
        rr = [r for r in rows if r["date"] == d]
        b = 2.0 if bump_from and d >= bump_from else 1.0
        adv[d] = resp(["PLAYER_ID", "USG_PCT", "AST_PCT", "OREB_PCT", "DREB_PCT", "TM_TOV_PCT", "PIE", "POSS"],
                      [[r["pid"], .2 * b, .1, .05, .15, .1, .1, r["min"] * 2] for r in rr])
        usage[d] = resp(["PLAYER_ID", "PCT_FGA", "PCT_FG3A", "PCT_FTA", "PCT_AST", "PCT_REB", "PCT_TOV", "PCT_STL",
                         "PCT_BLK", "PCT_PTS"], [[r["pid"]] + [.2] * 9 for r in rr])
        st[d] = resp(["PLAYER_ID", "TEAM_ID", "TEAM_ABBREVIATION"],
                     [[r["pid"], 1 if r["team"] == "AAA" else 2, r["team"]] for r in rr if r["pid"] % 10 in (1, 2, 3, 4, 5)][:10])
    return {"adv": adv, "usage": usage, "starters": st}


def test_features_use_earlier_dates_only():
    rows = synth()
    raw = synth_raw(rows)
    X, names, fams, _ = FT.build(rows, raw, families=("F0", "F1"))
    cut = "2024-01-20"
    rows2 = copy.deepcopy(rows)
    for r in rows2:
        if r["date"] >= cut:
            r.update(min=r["min"] + 7, pts=r["pts"] + 9, fga=r["fga"] * 3, tov=5.0)
    X2, *_ = FT.build(rows2, synth_raw(rows2, bump_from=cut), families=("F0", "F1"))
    early = np.array([r["date"] <= cut for r in rows])
    assert np.allclose(X[early], X2[early])                 # nothing from date >= d reaches a date-d feature
    late = np.array([r["date"] > "2024-01-21" for r in rows])
    assert not np.allclose(X[late], X2[late])               # ...and the change does show up afterwards


def test_f0_proxy_uses_presence_and_starts_not_outcomes():
    rows = synth()
    X, names, *_ = FT.build(rows, synth_raw(rows), families=("F0",))
    d, star = "2024-01-25", 1                                  # AAA's 36-minute regular sits out on the 25th
    rows_b = synth(skip={(d, star)})
    Xb, *_ = FT.build(rows_b, synth_raw(rows_b), families=("F0",))
    i_out = names.index("F0:mates_out_n")
    mates = [k for k, r in enumerate(rows_b) if r["date"] == d and r["team"] == "AAA"]
    assert all(Xb[k, i_out] == 1 for k in mates)
    opp = [k for k, r in enumerate(rows_b) if r["date"] == d and r["team"] == "BBB"]
    assert all(Xb[k, names.index("F0:opp_out_n")] == 1 for k in opp)
    rows_c = copy.deepcopy(rows)                               # same presence, different minutes and stats that day
    for r in rows_c:
        if r["date"] == d:
            r.update(min=1.0, pts=0.0, fga=0.0)
    Xc, *_ = FT.build(rows_c, synth_raw(rows_c), families=("F0",))
    same_day = np.array([r["date"] == d for r in rows])
    assert np.allclose(X[same_day], Xc[same_day])


def test_missing_feed_columns_are_dropped_and_listed():
    rows = synth()
    raw = synth_raw(rows)
    for j in raw["adv"].values():
        j["resultSets"][0]["headers"][1] = "SOMETHING_ELSE"     # USG_PCT no longer present
    X, names, fams, rep = FT.build(rows, raw, families=("F1",))
    assert "adv.USG_PCT" in rep["missing_columns"]["F1"] and not any("USG_PCT" in n for n in names)


def test_residual_walk_uses_earlier_months_only():
    rng = np.random.default_rng(1)
    date = np.array([f"2023-{m:02d}-{d:02d}" for m in (1, 2, 3, 4) for d in range(1, 29)] * 20)
    X = rng.normal(size=(len(date), 4))
    R = X @ rng.normal(size=(4, 8)) * .1 + rng.normal(size=(len(date), 8)) * .05
    old = P.FIRST_FIT
    P.FIRST_FIT = "2023-02-01"
    try:
        a = P.residual_walk(date, X, R, 1)
        R2 = R.copy()
        R2[date >= "2023-03-01"] += 5                          # change March and April outcomes
        b = P.residual_walk(date, X, R2, 1)
    finally:
        P.FIRST_FIT = old
    upto = date < "2023-04-01"                                 # Jan (no fit), Feb, Mar predictions unchanged
    assert np.allclose(a[upto], b[upto]) and not np.allclose(a[~upto], b[~upto])
    assert np.all(a[date < "2023-02-01"] == 0)


def test_zero_effect_is_proj10_and_holm():
    mu = np.array([[30.0, 15, 6, 4, 1.5, 1, .5, 2], [0.0, 0, 0, 0, 0, 0, 0, 0]])
    assert np.allclose(P.apply_residual(mu, np.zeros_like(mu)), mu)
    up = P.apply_residual(mu, np.full_like(mu, .1))
    assert up[0, 0] > 30 and up[0, 1] > 15 * 1.2               # minutes effect carries into the counts
    h = P.holm({"a": .001, "b": .02, "c": .04})
    assert h == {"a": True, "b": True, "c": True}
    assert P.holm({"a": .001, "b": .04, "c": .03}) == {"a": True, "b": False, "c": False}


def test_boot_is_date_clustered():
    d = np.array(["x"] * 50 + ["y"] * 50)
    b = P.boot(np.r_[np.full(50, -1.0), np.full(50, 1.0)], d, reps=500)
    assert b["mean"] == pytest.approx(0) and b["lo"] < 0 < b["hi"]


def test_lineup_poll_stores_only_changes():
    import sqlite3, tempfile, pathlib, datetime as dt
    import nba_lineups_poll as L

    class R:
        def __init__(self, j):
            self.status_code, self._j = 200, j

        def json(self):
            return self._j
    con = sqlite3.connect(pathlib.Path(tempfile.mkdtemp()) / "l.sqlite")
    con.execute(L.DDL)
    t = dt.datetime(2026, 10, 26, 22, 0, tzinfo=dt.timezone.utc)
    j1, j2 = {"games": [{"gameId": "G", "x": 1}]}, {"games": [{"gameId": "G", "x": 2}]}
    assert L.poll_once(con, lambda u: R(j1), t) == "stored"
    assert L.poll_once(con, lambda u: R(j1), t + dt.timedelta(minutes=5)) == "same"
    assert L.poll_once(con, lambda u: R(j2), t + dt.timedelta(minutes=10)) == "stored"
    assert L.poll_once(con, lambda u: R(j2), t + dt.timedelta(minutes=80)) == "stored"      # hourly heartbeat
    assert L.et_date(dt.datetime(2026, 10, 27, 2, 0, tzinfo=dt.timezone.utc)) == "2026-10-26"
    assert L.et_date(dt.datetime(2026, 11, 3, 4, 30, tzinfo=dt.timezone.utc)) == "2026-11-02"   # EST: UTC-5
    assert L.et_date(dt.datetime(2027, 3, 8, 3, 30, tzinfo=dt.timezone.utc)) == "2027-03-07"
