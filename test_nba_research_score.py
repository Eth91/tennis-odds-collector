"""nba_research_score: the nightly replay that grades the research page's signals against results and the price.
Point-in-time rules: the board as of the last change BEFORE tip, history strictly before the game date, the injury
report published before tip; DNPs and pushes are void."""
import pathlib
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_matchup as MU
import nba_research_score as SC

TARGET = ("G9", "2026-10-25", "2026-10-26T00:00:00Z")          # gid, date, tip


def fixture():
    d = pathlib.Path(tempfile.mkdtemp())
    q = sqlite3.connect(d / "lines.sqlite")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT, stat TEXT, "
              "line REAL, side TEXT, odds REAL)")
    gid, _, tip = TARGET
    rows = [("2026-10-25T12:00:00", "fd", 1, "points", 19.5, "over", 1.9), ("2026-10-25T12:00:00", "fd", 1, "points", 19.5, "under", 1.9),
            ("2026-10-25T20:00:00", "fd", 1, "points", 20.5, "over", 1.95), ("2026-10-25T20:00:00", "fd", 1, "points", 20.5, "under", 1.87),
            ("2026-10-25T20:00:00", "fd", 1, "points", 19.5, "over", None), ("2026-10-25T20:00:00", "fd", 1, "points", 19.5, "under", None),
            ("2026-10-25T21:00:00", "dk", 1, "points", 20.5, "over", 1.9), ("2026-10-25T21:00:00", "dk", 1, "points", 20.5, "under", 1.9),
            ("2026-10-26T00:30:00", "fd", 1, "points", 30.5, "over", 1.9), ("2026-10-26T00:30:00", "fd", 1, "points", 30.5, "under", 1.9),
            ("2026-10-25T20:00:00", "fd", 2, "points", 9.5, "over", 1.9), ("2026-10-25T20:00:00", "fd", 2, "points", 9.5, "under", 1.9),
            ("2026-10-25T20:00:00", "fd", 3, "rebounds", 6.0, "over", 1.9), ("2026-10-25T20:00:00", "fd", 3, "rebounds", 6.0, "under", 1.9)]
    q.executemany("INSERT INTO quotes VALUES (?,?,?,?,?,'',?,?,?,?)", [(t, b, gid, tip, p, s, l, sd, o) for t, b, p, s, l, sd, o in rows])
    q.commit()
    n = sqlite3.connect(d / "news.sqlite")
    n.execute("CREATE TABLE snapshots (mark TEXT, published_at TEXT, game_date TEXT, matchup TEXT, team TEXT, pid INTEGER, "
              "player TEXT, status TEXT, reason TEXT)")
    n.execute("INSERT INTO snapshots VALUES ('m1','2026-10-25T18:00:00+00:00','2026-10-25','','PHX',4,'Mate','Out','')")
    n.execute("INSERT INTO snapshots VALUES ('m2','2026-10-26T01:00:00+00:00','2026-10-25','','PHX',5,'Late','Out','')")   # after tip
    n.commit()
    m = MU.connect(d / "matchup.sqlite")
    PG = "INSERT INTO player_games (gid, team, pid, pos, starter, min, pts, reb, ast, fg3m, stl, blk, tov, fga, fg3a, fta) " \
         "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    games = [(f"0022500{i:03d}", "2025-26", f"2026-0{1 + i // 28}-{1 + i % 28:02d}") for i in range(12)]
    games += [("0022600001", "2026-27", "2026-10-22"), (gid, "2026-27", "2026-10-25"), ("0022600099", "2026-27", "2026-10-28")]
    for i, (g, season, date) in enumerate(games):
        m.execute("INSERT INTO games VALUES (?,?,?,?,?,?,?)", (g, season, date, "PHX", "UTA", 110, 100))
        for t in ("PHX", "UTA"):
            m.execute("INSERT INTO team_games VALUES (?,?,?,90,20,10,12)", (g, t, "UTA" if t == "PHX" else "PHX"))
        pts = 25 if g == gid else 99 if date > "2026-10-25" else 18 + i % 3       # a future game scores 99: never seen
        m.execute(PG, (g, "PHX", 1, "SG", 1, 34, pts, 4, 5, 2, 1, 0, 2, 16, 6, 4))
        m.execute(PG, (g, "PHX", 4, "C", 1, 30, 10, 9, 2, 0, 1, 1, 1, 9, 0, 3))   # the teammate who is out on G9
        if g != gid:
            m.execute(PG, (g, "PHX", 3, "PF", 1, 28, 9, 6, 1, 0, 0, 0, 1, 8, 1, 2))
        else:
            m.execute(PG, (g, "PHX", 3, "PF", 1, 28, 9, 6, 1, 0, 0, 0, 1, 8, 1, 2))  # 6 rebounds on a 6.0 line: push
    m.execute("DELETE FROM player_games WHERE gid=? AND pid=4", (gid,))           # out that night
    m.commit()
    return d


def test_boards_before_tip_carry_forward_and_stop_at_tip():
    d = fixture()
    b = SC.boards_before_tip(sqlite3.connect(d / "lines.sqlite"), [TARGET[0]])
    fd = b[(TARGET[0], 1, "points", "fd")]
    assert fd["open"] == (19.5, 1.9, 1.9)                                   # first two-sided main
    assert set(fd["close"]) == {(20.5, "over"), (20.5, "under")}           # 19.5 pulled; the 00:30 rung is after tip


def test_report_before_tip_only():
    d = fixture()
    r = SC.report_before(sqlite3.connect(d / "news.sqlite"), "2026-10-25", "2026-10-26T00:00:00+00:00")
    assert dict(r) == {"PHX": [4]}                                          # the 01:00 snapshot is after tip


def test_grade_point_in_time_and_voids():
    d = fixture()
    recs = SC.grade(lines=d / "lines.sqlite", matchup=d / "matchup.sqlite", news=d / "news.sqlite", season="2026-27")
    by = {(r["pid"], r["stat"]): r for r in recs}
    assert (2, "points") not in by                                          # never played: void
    assert (3, "rebounds") not in by                                        # 6 on a 6.0 line: push, void
    r = by[(1, "points")]
    fair = ((1 / 1.95) / (1 / 1.95 + 1 / 1.87) + .5) / 2                    # FD and DK at 20.5
    assert r["line"] == 20.5 and r["over"] is True and r["fair"] == pytest.approx(fair) and r["nbooks"] == 2
    assert r["l10"] == (0, 10)                                              # 18-20 before; the future 99 never counted
    assert r["szn"] == (0, 1) and r["move"] == 1.0                          # one game this season; FD 19.5 -> 20.5
    assert r["mate_out"] is True                                            # player 4 (30 min, 13 games) out pre-tip


def test_score_verdicts():
    rec = lambda over, fair: {"over": over, "fair": fair, "books": {}, "line": 1.5}
    many_wins = [(rec(True, .5), "over")] * 80 + [(rec(False, .5), "over")] * 40
    assert SC.score(many_wins, "x", "")["verdict"] == "helps"
    assert SC.score(many_wins[:30], "x", "")["verdict"] == "too few picks"
    coin = [(rec(True, .5), "over")] * 60 + [(rec(False, .5), "over")] * 60
    assert SC.score(coin, "x", "")["verdict"] == "no edge yet"
    assert SC.score([], "x", "")["verdict"] == "no picks yet"


def test_mutants_score_leakage():
    import importlib
    src = pathlib.Path(SC.__file__).read_text()
    for tag, a, b, test in (
            ("history includes game day", 'for r in logs.get(pid, []) if r[0] < date]', 'for r in logs.get(pid, []) if r[0] <= date]',
             test_grade_point_in_time_and_voids),
            ("prices after tip", "            if not tip or t >= tip:\n", "            if not tip:\n",
             test_boards_before_tip_carry_forward_and_stop_at_tip)):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_research_score.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        saved = sys.modules.pop("nba_research_score")
        try:
            globals()["SC"] = importlib.import_module("nba_research_score")
            with pytest.raises(AssertionError):
                test()
        finally:
            globals()["SC"] = saved
            sys.modules["nba_research_score"] = saved
            sys.path.remove(str(d))
