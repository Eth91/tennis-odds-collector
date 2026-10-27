"""T4-live: the board is FanDuel and DraftKings as of tip − 30 from the change log; signal when FanDuel's no-vig
P(side) × DraftKings' odds − 1 > 0.02; DNP void, push 0; only games since the prereg's start; no evidence, no verdict."""
import pathlib
import sqlite3
import tempfile

import pytest

import nba_project as NP
import nba_t4_live as T


def stores(d):
    q = sqlite3.connect(d / "lines.sqlite")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT, stat TEXT, "
              "line REAL, side TEXT, odds REAL)")
    tip = "2026-10-29T00:00:00Z"
    ins = lambda t, bk, gid, pid, line, side, odds, tp=tip: q.execute("INSERT INTO quotes VALUES (?,?,?,?,?,'','points',?,?,?)",
                                                                     (t, bk, gid, tp, pid, line, side, odds))
    for side in ("over", "under"):
        ins("2026-10-28T20:00:00", "fd", "G", 1, 20.5, side, 1.9)             # FanDuel fair .5/.5
        ins("2026-10-28T20:00:00", "fd", "G", 2, 9.5, side, 1.9)
    ins("2026-10-28T20:00:00", "dk", "G", 1, 20.5, "over", 2.1)                # EV .05 -> signal (over)
    ins("2026-10-28T20:00:00", "dk", "G", 1, 20.5, "under", 1.7)               # EV -.15 -> none
    ins("2026-10-28T23:45:00", "dk", "G", 2, 9.5, "over", 2.2)                 # after tip − 30: ignored
    ins("2026-10-28T23:50:00", "fd", "G", 1, 20.5, "over", 1.8)                # FanDuel moves toward over before tip (CLV +)
    ins("2026-10-28T23:50:00", "fd", "G", 1, 20.5, "under", 2.0)
    for side in ("over", "under"):                                            # a game before the start: never counted
        ins("2026-10-26T20:00:00", "fd", "OLD", 1, 20.5, side, 1.9, "2026-10-27T00:00:00Z")
    ins("2026-10-26T20:00:00", "dk", "OLD", 1, 20.5, "over", 2.2, "2026-10-27T00:00:00Z")
    q.commit()
    m = sqlite3.connect(d / "mu.sqlite")
    m.execute("CREATE TABLE games (gid TEXT, season TEXT, date TEXT, home TEXT, away TEXT, home_pts REAL, away_pts REAL)")
    m.execute("CREATE TABLE player_games (gid TEXT, team TEXT, pid INTEGER, pos TEXT, starter INTEGER, min REAL, pts REAL, "
              "reb REAL, ast REAL, fg3m REAL, stl REAL, blk REAL, tov REAL, fga REAL, fg3a REAL, fta REAL)")
    m.execute("INSERT INTO games VALUES ('G','2026-27','2026-10-28','AAA','BBB',100,99)")
    m.execute("INSERT INTO games VALUES ('OLD','2026-27','2026-10-26','AAA','BBB',100,99)")
    m.execute("INSERT INTO player_games VALUES ('G','AAA',1,'G',1,34,25,0,0,0,0,0,0,0,0,0)")
    m.execute("INSERT INTO player_games VALUES ('OLD','AAA',1,'G',1,34,25,0,0,0,0,0,0,0,0,0)")
    m.commit()


def test_signals_rule_cutoff_and_since():
    d = pathlib.Path(tempfile.mkdtemp())
    stores(d)
    sig, n = T.signals(d / "lines.sqlite", d / "mu.sqlite")
    assert [(s["gid"], s["pid"], s["side"]) for s in sig] == [("G", 1, "over")]
    s = sig[0]
    assert s["ev_fd"] == pytest.approx(0.5 * 2.1 - 1) and s["result"] == "win" and s["profit"] == pytest.approx(1.1)
    assert s["clv"] == pytest.approx(NP.no_vig(1.8, 2.0) - 0.5) and s["clv"] > 0
    r = T.grade(d / "lines.sqlite", d / "mu.sqlite", d / "o.json")
    assert r["graded"] == 1 and r["verdict"].startswith("not enough prospective evidence")
