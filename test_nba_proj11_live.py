"""proj-1.1 live path: refresh then forecast on synthetic data. Game-day inputs come only from what was visible at
the forecast time (lineup snapshot, official report); nothing is logged after tip − 30; proj-1.0's log is
untouched; no evidence means no verdict."""
import datetime as dt
import json
import pathlib
import sqlite3
import tempfile
import zlib

import numpy as np

import nba_proj11_live as L
import test_nba_proj11 as T

UTC = dt.timezone.utc


def setup(tmp):
    rows = T.synth()
    for r in rows:
        r.update(season="2022-23", team_poss=100.0)
    raw = T.synth_raw(rows)
    cfg = {"kept": ["F0", "F1"], "lambda": 10, "blend_w": 0.85}
    (tmp / "cfg.json").write_text(json.dumps(cfg))
    cfg = L.load_config(tmp / "cfg.json")
    targets = [{"gid": "G", "date": "2024-02-01", "pid": p, "team": t, "opp": o, "home": int(t == "AAA")}
               for t, o in (("AAA", "BBB"), ("BBB", "AAA")) for p in T.TEAMS[t]]
    return rows, raw, cfg, targets


def lineup_db(path, snaps):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE snaps (fetched_at TEXT, date_et TEXT, sha TEXT, body BLOB)")
    for at, aaa_starters, inactive in snaps:
        game = {"gameId": "G", "homeTeam": {"teamAbbreviation": "AAA", "players": [
            {"personId": p, "position": "G" if p in aaa_starters else "", "lineupStatus": "Expected",
             "rosterStatus": "Inactive" if p in inactive else "Active"} for p in T.TEAMS["AAA"]]},
            "awayTeam": {"teamAbbreviation": "BBB", "players": [
                {"personId": p, "position": "F" if p in (12, 13, 14, 15, 16) else "", "lineupStatus": "Expected",
                 "rosterStatus": "Active"} for p in T.TEAMS["BBB"]]}}
        con.execute("INSERT INTO snaps VALUES (?,?,?,?)", (at, "2024-02-01", "x", zlib.compress(json.dumps({"games": [game]}).encode())))
    con.commit()


def news_db(path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE snapshots (mark TEXT, published_at TEXT, game_date TEXT, matchup TEXT, team TEXT, pid INTEGER, "
                "player TEXT, status TEXT, reason TEXT)")
    con.execute("INSERT INTO snapshots VALUES ('m','2024-02-01T20:00:00+00:00','2024-02-01','','BBB',11,'','Out','')")
    con.commit()


def test_refresh_forecast_and_cutoff():
    tmp = pathlib.Path(tempfile.mkdtemp())
    rows, raw, cfg, targets = setup(tmp)
    st = L.refresh11(targets, rows=rows, raw=raw, cfg=cfg, cache=tmp / "c.pkl")
    assert st.startswith("projected 12 players")
    assert L.refresh11(targets, rows=rows, raw=raw, cfg=cfg, cache=tmp / "c.pkl").startswith("cache current")
    lineup_db(tmp / "l.sqlite", [("2024-02-01T23:00:00+00:00", {2, 3, 4, 5, 6}, {1}),     # star 1 inactive
                                 ("2024-02-02T00:20:00+00:00", {1, 3, 4, 5, 6}, set())])   # seen only later
    news_db(tmp / "n.sqlite")
    (tmp / "props.json").write_text(json.dumps({
        "games": [{"gid": "G", "utc": "2024-02-02T01:00:00Z"}],
        "props": [{"gid": "G", "pid": 2, "market": "points", "books": {"fd": {"main": 15.5, "rungs": [[15.5, 1.9, 1.9]]}}},
                  {"gid": "G", "pid": 12, "market": "rebounds", "books": {"dk": {"main": 4.5, "rungs": [[4.5, 1.8, 2.0]]}}}]}))
    kw = dict(cfg=cfg, cache=tmp / "c.pkl", lineups_db=tmp / "l.sqlite", news_db=tmp / "n.sqlite", log_db=tmp / "log.sqlite",
              props_path=tmp / "props.json")
    out = L.forecast11(now=dt.datetime(2024, 2, 1, 23, 30, tzinfo=UTC), **kw)
    assert out.startswith("logged 2 forecasts")
    con = sqlite3.connect(tmp / "log.sqlite")
    inp = {pid: (lu, st_, mo, oo) for pid, lu, st_, mo, oo in con.execute("SELECT pid, lineup, starts, mates_out, opp_out FROM p11_inputs")}
    assert inp[2] == ("Expected", 1.0, 1, 1)          # starts (23:00 snapshot), star out, BBB's 11 listed Out
    assert inp[12][2:] == (1, 1)                        # BBB: its regular 11 out; AAA's star out for the opponent
    v = {r[0] for r in con.execute("SELECT DISTINCT version FROM forecasts")}
    assert v == {cfg["version"]} and cfg["version"].startswith("proj-1.1-dev:")
    p = dict(con.execute("SELECT pid, p_over FROM forecasts WHERE kind='cutoff'"))
    assert 0 < p[2] < 1 and 0 < p[12] < 1
    late = L.forecast11(now=dt.datetime(2024, 2, 2, 0, 31, tzinfo=UTC), **kw)            # past tip − 30
    assert late.startswith("logged 0 forecasts")
    assert dict(con.execute("SELECT pid, starts FROM p11_inputs"))[2] == 1.0             # the 00:20 snapshot never used


def test_no_evidence_no_verdict():
    tmp = pathlib.Path(tempfile.mkdtemp())
    rows, raw, cfg, targets = setup(tmp)
    for f in ("log.sqlite", "lines.sqlite", "mu.sqlite"):
        sqlite3.connect(tmp / f).close()
    out = L.prospective11(tmp / "o.json", cfg=cfg, log_db=tmp / "log.sqlite", lines_db=tmp / "lines.sqlite",
                          matchup_db=tmp / "mu.sqlite")
    assert all("not enough prospective evidence" in v for v in out["verdicts"])


def test_nothing_kept_nothing_runs():
    tmp = pathlib.Path(tempfile.mkdtemp())
    (tmp / "cfg.json").write_text(json.dumps({"kept": [], "lambda": 10, "blend_w": .85}))
    assert "nothing to run" in L.refresh11([], cfg=L.load_config(tmp / "cfg.json"), cache=tmp / "c.pkl")
