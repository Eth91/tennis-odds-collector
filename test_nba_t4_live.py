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


def test_t5_first_under_edge_one_per_prop():
    d = pathlib.Path(tempfile.mkdtemp())
    stores(d)
    q = sqlite3.connect(d / "lines.sqlite")
    tip = "2026-10-29T00:00:00Z"
    ins = lambda t, bk, line, side, odds: q.execute("INSERT INTO quotes VALUES (?,?,?,?,?,'','points',?,?,?)",
                                                   (t, bk, "G", tip, 3, line, side, odds))
    ins("2026-10-28T15:00:00", "fd", 12.5, "over", 1.8); ins("2026-10-28T15:00:00", "fd", 12.5, "under", 2.0)  # FD under fair ~.474
    ins("2026-10-28T15:00:00", "dk", 12.5, "under", 2.1)                      # EV .474*2.1-1 = -.004: no
    ins("2026-10-28T17:00:00", "dk", 12.5, "under", 2.3)                      # EV +.09: the first signal (7 h before tip)
    ins("2026-10-28T19:00:00", "dk", 12.5, "under", 2.5)                      # later, bigger edge: not counted again
    q.commit()
    m = sqlite3.connect(d / "mu.sqlite")
    m.execute("INSERT INTO player_games VALUES ('G','AAA',3,'G',1,30,10,0,0,0,0,0,0,0,0,0)")   # 10 < 12.5: under wins
    m.commit()
    sig, _ = T.signals_t5(d / "lines.sqlite", d / "mu.sqlite")
    s3 = [s for s in sig if s["pid"] == 3]
    assert len(s3) == 1 and s3[0]["odds"] == 2.3 and s3[0]["min_before_tip"] == 420 and s3[0]["result"] == "win"
    assert all(s["side"] == "under" for s in sig)
    assert not [s for s in sig if s["gid"] == "OLD"]                           # before the start date: not counted


def test_t5b_confirmation_status_and_model_filters():
    d = pathlib.Path(tempfile.mkdtemp())
    stores(d)
    q = sqlite3.connect(d / "lines.sqlite")
    q.execute("CREATE TABLE cycles (ts TEXT, book TEXT, status TEXT, rows INTEGER, events INTEGER, matched_events INTEGER, "
              "resolved INTEGER, unresolved INTEGER, detail TEXT)")
    for ts in ("2026-10-28T15:00:00", "2026-10-28T15:10:00", "2026-10-28T17:00:00", "2026-10-28T17:10:00"):
        q.execute("INSERT INTO cycles VALUES (?, 'fd', 'ok', 0, 0, 0, 0, 0, '')", (ts,))
    tip = "2026-10-29T00:00:00Z"
    ins = lambda t, bk, pid, line, side, odds: q.execute("INSERT INTO quotes VALUES (?,?,?,?,?,'','points',?,?,?)",
                                                        (t, bk, "G", tip, pid, line, side, odds))
    for pid in (5, 6, 7, 8):
        ins("2026-10-28T15:00:00", "fd", pid, 12.5, "over", 1.9); ins("2026-10-28T15:00:00", "fd", pid, 12.5, "under", 1.9)
        ins("2026-10-28T15:05:00", "dk", pid, 12.5, "under", 2.2)             # trigger at 15:05 (EV .10)
    ins("2026-10-28T15:08:00", "dk", 6, 12.5, "under", 1.9)                   # pid 6 reverts before FD's next poll
    q.commit()
    m = sqlite3.connect(d / "mu.sqlite")
    for pid in (5, 6, 7, 8):
        m.execute("INSERT INTO player_games VALUES ('G','AAA',?,'G',1,30,10,0,0,0,0,0,0,0,0,0)", (pid,))
    m.commit()
    n = sqlite3.connect(d / "news.sqlite")
    n.execute("CREATE TABLE snapshots (mark TEXT, published_at TEXT, game_date TEXT, matchup TEXT, team TEXT, pid INTEGER, "
              "player TEXT, status TEXT, reason TEXT)")
    n.execute("INSERT INTO snapshots VALUES ('m','2026-10-28T14:00:00+00:00','2026-10-28','','AAA',7,'','Questionable','')")
    n.commit()
    model = lambda s, t: 0.40 if s["pid"] == 8 else 0.60                       # pid 8: the model leans over
    sig, cnt = T.signals_t5b(d / "lines.sqlite", d / "mu.sqlite", d / "news.sqlite", model_p_under=model)
    got = {s["pid"]: s for s in sig}
    assert set(got) == {5} and got[5]["seen_at"] == "2026-10-28T15:10:00" and got[5]["odds"] == 2.2
    assert cnt["fail_confirm"] >= 1 and cnt["fail_status"] == 1 and cnt["fail_model"] >= 1
