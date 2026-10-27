"""S1: a regular newly Out on a report -> teammates' stale FanDuel props where the model beats FanDuel by >= 0.05 are
logged once per event; grading takes CLV at tip − 30 and ROI at the signal price."""
import datetime as dt
import pathlib
import sqlite3
import tempfile

import pytest

import nba_news_window as W
import nba_project as NP

UTC = dt.timezone.utc


def build(d):
    m = sqlite3.connect(d / "mu.sqlite")
    m.execute("CREATE TABLE games (gid TEXT, season TEXT, date TEXT, home TEXT, away TEXT, home_pts REAL, away_pts REAL)")
    m.execute("CREATE TABLE player_games (gid TEXT, team TEXT, pid INTEGER, pos TEXT, starter INTEGER, min REAL, pts REAL, "
              "reb REAL, ast REAL, fg3m REAL, stl REAL, blk REAL, tov REAL, fga REAL, fg3a REAL, fta REAL)")
    for k, d_ in enumerate(("2026-10-24", "2026-10-25", "2026-10-26")):              # X (pid 1) averages 34 min
        m.execute("INSERT INTO games VALUES (?,'2026-27',?,'AAA','BBB',100,99)", (f"P{k}", d_))
        m.execute("INSERT INTO player_games VALUES (?, 'AAA', 1, 'G', 1, 34, 20,0,0,0,0,0,0,0,0,0)", (f"P{k}",))
    m.execute("INSERT INTO games VALUES ('G','2026-27','2026-10-28','AAA','BBB',100,99)")
    m.execute("INSERT INTO player_games VALUES ('G','AAA',2,'G',1,36,20,0,0,0,0,0,0,0,0,0)")         # teammate T: 20 pts
    m.commit()
    n = sqlite3.connect(d / "news.sqlite")
    n.execute("CREATE TABLE snapshots (mark TEXT, published_at TEXT, game_date TEXT, matchup TEXT, team TEXT, pid INTEGER, "
              "player TEXT, status TEXT, reason TEXT)")
    n.execute("CREATE TABLE triggers (mark TEXT, published_at TEXT, detected_at TEXT, fresh TEXT, lines_at TEXT, flags_at TEXT, "
              "n_flags INTEGER, note TEXT)")
    n.execute("INSERT INTO snapshots VALUES ('r1','2026-10-28T18:00:04+00:00','2026-10-28','','AAA',1,'X','Questionable','')")
    n.execute("INSERT INTO snapshots VALUES ('r2','2026-10-28T20:00:04+00:00','2026-10-28','','AAA',1,'X','Out','')")
    n.execute("INSERT INTO triggers VALUES ('r2','2026-10-28T20:00:04+00:00','x','[]','2026-10-28T20:00:30+00:00','x',0,'')")
    n.commit()
    q = sqlite3.connect(d / "lines.sqlite")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT, stat TEXT, "
              "line REAL, side TEXT, odds REAL)")
    tip = "2026-10-29T00:00:00Z"
    ins = lambda t, line, side, odds: q.execute("INSERT INTO quotes VALUES (?,'fd','G',?,2,'','points',?,?,?)", (t, tip, line, side, odds))
    ins("2026-10-28T19:00:00", 15.5, "over", 1.9); ins("2026-10-28T19:00:00", 15.5, "under", 1.9)
    ins("2026-10-28T21:00:00", 15.5, "over", 1.6); ins("2026-10-28T21:00:00", 15.5, "under", 2.3)   # FanDuel catches up later
    q.commit()


def test_s1_process_and_grade():
    d = pathlib.Path(tempfile.mkdtemp())
    build(d)
    model = lambda e, wanted: {w: 0.60 for w in wanted}                               # P(over) .60 vs FanDuel .50
    out = W.process(now=dt.datetime(2026, 10, 28, 20, 1, tzinfo=UTC), news_db=d / "news.sqlite", lines_db=d / "lines.sqlite",
                    log_db=d / "log.sqlite", matchup_db=d / "mu.sqlite", model_fn=model, cfg_path=pathlib.Path("nba_proj11_config.json"))
    assert "logged 1 S1 signal" in out
    again = W.process(now=dt.datetime(2026, 10, 28, 20, 2, tzinfo=UTC), news_db=d / "news.sqlite", lines_db=d / "lines.sqlite",
                      log_db=d / "log.sqlite", matchup_db=d / "mu.sqlite", model_fn=model, cfg_path=pathlib.Path("nba_proj11_config.json"))
    assert again == "no new report"
    r = W.grade(d / "log.sqlite", d / "lines.sqlite", d / "mu.sqlite")
    assert r["graded"] == 1 and r["roi"]["mean"] == pytest.approx(0.9)
    assert r["clv"]["mean"] == pytest.approx(NP.no_vig(1.6, 2.3) - 0.5) and r["clv"]["mean"] > 0
    assert r["verdict"].startswith("not enough prospective evidence")
