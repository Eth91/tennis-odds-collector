"""Amendment 30: box parsing, point-in-time pace and matchup factors (no future games, shrinkage, position groups),
and the play-type scheme cell. MUTANTS in test_mutants()."""
import importlib
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_matchup as MU


def box(gid, date_utc, home, away, h_stats, a_stats, h_players, a_players, status=3):
    mk = lambda ps: [{"personId": pid, "position": pos, "starter": "1" if st else "0", "played": "1",
                      "statistics": {"minutes": "PT30M00.00S", "points": pts, "reboundsTotal": reb, "assists": ast}}
                     for pid, pos, st, pts, reb, ast in ps]
    tm = lambda tri, s, ps: {"teamTricode": tri, "players": mk(ps), "statistics": {
        "fieldGoalsAttempted": s[0], "freeThrowsAttempted": s[1], "reboundsOffensive": s[2], "turnovers": s[3]}}
    return {"gameId": gid, "gameStatus": status, "gameTimeUTC": date_utc,
            "homeTeam": tm(home, h_stats, h_players), "awayTeam": tm(away, a_stats, a_players)}


# OPP plays fast (~110 possessions) and gives guards 40 points; the other teams play ~90 and give guards 20.
BOXES = [
    box("0022300001", "2023-11-01T23:00:00Z", "OPP", "AAA", (100, 25, 10, 9), (100, 25, 10, 9),
        [(1, "PG", 1, 20, 3, 8), (2, "C", 1, 10, 12, 2)], [(3, "PG", 1, 40, 4, 6), (4, "C", 1, 12, 10, 1)]),
    box("0022300002", "2023-11-02T23:00:00Z", "BBB", "CCC", (80, 25, 10, 9), (80, 25, 10, 9),
        [(5, "SG", 1, 20, 3, 5), (6, "C", 1, 12, 11, 2)], [(7, "PG", 1, 20, 4, 5), (8, "C", 1, 10, 10, 1)]),
    box("0022300003", "2023-11-03T23:00:00Z", "OPP", "BBB", (100, 25, 10, 9), (100, 25, 10, 9),
        [(1, "PG", 1, 20, 3, 8), (2, "C", 1, 10, 12, 2)], [(5, "SG", 1, 40, 4, 6), (6, "C", 1, 12, 10, 1)]),
    box("0022300004", "2023-11-10T23:00:00Z", "OPP", "CCC", (200, 25, 10, 9), (200, 25, 10, 9),   # AFTER the date
        [(1, "PG", 1, 20, 3, 8), (2, "C", 1, 10, 12, 2)], [(7, "PG", 1, 90, 4, 6), (8, "C", 1, 12, 10, 1)]),
    box("0022300005", "2023-11-04T23:00:00Z", "AAA", "CCC", (80, 25, 10, 9), (80, 25, 10, 9), [], [], status=2),
]


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    con = mod.connect(pathlib.Path(tempfile.mkdtemp()) / "m.sqlite")
    by = {b["gameId"]: b for b in BOXES}
    stored, missed = mod.fetch(list(by), con, get=lambda g: by[g], workers=1)
    want((stored, missed) == (4, 1), "final games stored, a live one skipped")
    S = mod.Season(con, "2023-24", index_pos={9: "G-F"})
    pace, mf = S.factors("OPP", "2023-11-05", 7)          # B = player 7 (a PG) facing OPP on 11/05
    lg = S._league_before("2023-11-05")
    want(lg[0] == 6 and abs(lg[1] - (4 * 110.0 + 2 * 90.0) / 6) < 1e-6, "league: 6 team-games before 11/05 (not the 11/10 game)")
    n, lg_poss = 2, lg[1]
    want(abs(pace - (n * 110.0 + 10 * lg_poss) / (n + 10) / lg_poss) < 1e-9, "pace factor = OPP's possessions, shrunk k=10")
    lg_g = lg[2][("G", "pts")]
    opp_g = (40 + 40) / 220.0
    want(abs(mf["pts"] - (n * opp_g + 10 * lg_g) / (n + 10) / lg_g) < 1e-9, "matchup: points allowed to guards per possession, shrunk")
    want(mf["pts"] > 1.0 and pace > 1.0, "a fast team that gives guards 40 is a plus matchup")
    want(S.group(5, "2023-11-05") == "G" and S.group(2, "2023-11-05") == "C", "position group from prior starts")
    want(S.group(9, "2023-11-05") == "G" and S.group(99, "2023-11-05") is None, "no start: index position, else none")
    p0, m0 = S.factors("OPP", "2023-11-01", 7)
    want(p0 == 1.0 and m0["pts"] == 1.0, "no prior games: factors are 1.0")
    _, m_none = S.factors("OPP", "2023-11-05", 99)
    want(m_none["pts"] == 1.0, "unknown position: no matchup adjustment")
    return ok


def test_factors():
    assert check(MU)


def test_scheme_cell():
    con = MU.connect(pathlib.Path(tempfile.mkdtemp()) / "m.sqlite")
    rows = [("2026-10-24", "2026-27", "player", "offensive", 7, "PHX", "PRBallHandler", 0.4, 0.9, 0.5, 80),
            ("2026-10-24", "2026-27", "player", "offensive", 7, "PHX", "Spotup", 0.2, 1.1, 0.7, 40),
            ("2026-10-24", "2026-27", "team", "defensive", 1, "OKC", "PRBallHandler", 0.1, 0.7, 0.9, 300),
            ("2026-10-24", "2026-27", "team", "defensive", 2, "UTA", "PRBallHandler", 0.1, 1.0, 0.1, 300)]
    con.executemany("INSERT INTO playtypes VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    assert MU.scheme_cell(con, 7, "OKC", "2026-10-25") == ("PRBallHandler", "tough")
    assert MU.scheme_cell(con, 7, "UTA", "2026-10-25") == ("PRBallHandler", "soft")
    assert MU.scheme_cell(con, 7, "OKC", "2026-10-23") == (None, None)       # no snapshot yet: never the future
    assert MU.scheme_cell(con, 8, "OKC", "2026-10-25") == (None, None)


def test_annotate30_information_only():
    import datetime as dt
    import sqlite3
    import nba_flags as F
    d = pathlib.Path(tempfile.mkdtemp())
    con = MU.connect(d / "m.sqlite")
    by = {b["gameId"]: b for b in BOXES}
    MU.fetch(list(by), con, get=lambda g: by[g], workers=1)
    con.executemany("INSERT INTO playtypes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [("2023-11-04", "2023-24", "player", "offensive", 7, "CCC", "Isolation", 0.3, 1.0, 0.5, 50),
                     ("2023-11-04", "2023-24", "team", "defensive", 1, "OPP", "Isolation", 0.1, 1.2, 0.2, 90)])
    con.commit(); con.close()
    q = sqlite3.connect(d / "l.sqlite")
    q.execute("CREATE TABLE game_lines (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, market TEXT, side TEXT, "
              "line REAL, odds REAL)")
    for gid, tot, sp in (("G1", 231.5, -11.5), ("G2", 220.5, -2.5), ("G3", 225.5, 4.0)):
        q.execute("INSERT INTO game_lines VALUES ('2023-11-05T18:00:00','fd',?, '', 'total', 'over', ?, 1.9)", (gid, tot))
        q.execute("INSERT INTO game_lines VALUES ('2023-11-05T18:00:00','fd',?, '', 'spread', 'away', ?, 1.9)", (gid, sp))
        q.execute("INSERT INTO game_lines VALUES ('2023-11-05T23:00:00','fd',?, '', 'total', 'over', 250, 1.9)", (gid,))  # later
    q.commit(); q.close()
    f = {"tier": "wowy", "team": "CCC", "matchup": "CCC @ OPP", "pid": 7, "stat": "pts", "gid": "G1", "proj": 20.0,
         "margin": 5.5, "line": 14.5}
    pr = {"tier": "priced", "team": "CCC", "matchup": "CCC @ OPP", "pid": 7, "stat": "points", "gid": "G1"}
    F.annotate30([f, pr], "2023-11-05", {}, dt.datetime(2023, 11, 5, 20, 0, tzinfo=dt.timezone.utc), {"G1", "G2", "G3"},
                 mdb=d / "m.sqlite", lines_db=d / "l.sqlite")
    assert f["pace_f"] > 1.0 and f["match_f"] > 1.0, f                  # player 7 started at PG
    assert (f["play_type"], f["scheme"]) == ("Isolation", "soft")
    assert f["g_total"] == 231.5 and f["total_cell"] == "HIGH" and f["g_spread"] == -11.5   # flag-time lines only
    assert f["proj"] == 20.0 and f["margin"] == 5.5 and "pace_f" not in pr               # nothing else changes


def test_mutants():
    src = pathlib.Path(MU.__file__).read_text()
    for tag, a, b in (
            ("future games leak", "i = bisect.bisect_left(self.dates[team], date)", "i = len(self.dates[team])"),
            ("league leak", "i = bisect.bisect_left(self.league_dates, date)", "i = len(self.league_dates)"),
            ("no shrinkage", "pace = (n * (poss / n) + K_SHRINK * lg_poss) / (n + K_SHRINK) / lg_poss",
             "pace = (poss / n) / lg_poss"),
            ("own team, not the opponent", "            defender = a if team == h else h\n", "            defender = team\n"),
            ("possessions without turnovers", "fga + 0.44 * fta - oreb + tov", "fga + 0.44 * fta - oreb")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_matchup_mut30.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_matchup_mut30")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_matchup_mut30", None)


if __name__ == "__main__":
    test_factors(); test_scheme_cell(); test_mutants()
    print("test_nba_matchup: OK")
