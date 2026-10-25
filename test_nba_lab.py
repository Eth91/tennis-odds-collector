"""Amendment 25: the stale-prop lab's grading (beat close, won, DNP), premise, excess bands, the box cache;
FanDuel game lines parsed from the league page and stored change-only, sides mapped to home / away /
over / under. MUTANTS in test_mutants()."""
import importlib
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_lines as L
import nba_stale_lab as LAB

PAGE = {"attachments": {
    "events": {"1": {"name": "Detroit Pistons @ Philadelphia 76ers"}, "2": {"name": "NBA Futures"}},
    "markets": {
        "a": {"eventId": 1, "marketType": "MATCH_HANDICAP_(2-WAY)", "marketStatus": "OPEN", "runners": [
            {"runnerName": "Detroit Pistons", "handicap": 1.5, "winRunnerOdds": {"americanDisplayOdds": {"americanOddsInt": -118}}},
            {"runnerName": "Philadelphia 76ers", "handicap": -1.5, "winRunnerOdds": {"americanDisplayOdds": {"americanOddsInt": -104}}}]},
        "b": {"eventId": 1, "marketType": "TOTAL_POINTS_(OVER/UNDER)", "marketStatus": "OPEN", "runners": [
            {"runnerName": "Over", "handicap": 224.5, "winRunnerOdds": {"americanDisplayOdds": {"americanOddsInt": -105}}},
            {"runnerName": "Under", "handicap": 224.5, "winRunnerOdds": {"americanDisplayOdds": {"americanOddsInt": -115}}}]},
        "c": {"eventId": 1, "marketType": "MONEY_LINE", "marketStatus": "SUSPENDED", "runners": []},
        "d": {"eventId": 2, "marketType": "NBA_SEED_O/U", "marketStatus": "OPEN", "runners": []}}}}
UPCOMING = [{"gid": "0022600117", "utc": "2026-10-25T23:30:00Z", "away_nick": "Pistons", "home_nick": "76ers"}]


def check(lab, lines):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    g = lab.grade(13.5, 1.85, (14.5, 2.00), 17)
    want(g[:3] == (True, False, True) and abs(g[3] - 0.85) < 1e-9,
         "over 13.5 -118, close 14.5: beat the close; 17 points: won +0.85u")
    want(lab.grade(13.5, 1.85, (13.5, 1.91), 12)[:3] == (False, False, False),
         "same line, longer over price at the close: did not beat it; 12: lost")
    want(lab.grade(13.5, 1.85, (13.5, 1.85), 13.5)[1:] == (True, False, 0.0), "unchanged close; exactly the line: a push")
    want([lab.band(x) for x in (None, -0.2, 0.4, 1.0)] == ["no projection", "< 0", "0-1", ">= 1"], "excess bands")
    bx = {1: {"name": "Joel Embiid", "_team": "PHI", "played": "1"}, 2: {"name": "Jalen Green", "_team": "PHX", "played": "0"}}
    want(lab.premise(bx, "PHI", "Joel Embiid") == "played" and lab.premise(bx, "PHX", "Jalen Green") == "sat"
         and lab.premise(bx, "DET", "Jalen Duren") == "sat", "premise: played / did not play / not in the box = sat")
    rows = lines.fd_game_lines(PAGE)
    want(sorted((r[1], r[2], r[3]) for r in rows) == [("spread", "Detroit Pistons", 1.5), ("spread", "Philadelphia 76ers", -1.5),
                                                     ("total", "Over", 224.5), ("total", "Under", 224.5)],
         "game lines: spread and total parsed; suspended and futures markets skipped")
    con = sqlite3.connect(":memory:")
    con.executescript(lines.DDL)
    a = lines.store_game_lines(con, PAGE, UPCOMING, "2026-10-25T20:00:00")
    b = lines.store_game_lines(con, PAGE, UPCOMING, "2026-10-25T20:10:00")
    sides = sorted(r[0] for r in con.execute("SELECT side FROM game_lines"))
    want((a, b) == (4, 0) and sides == ["away", "home", "over", "under"],
         f"stored change-only ({a}, {b}), sides home/away/over/under")
    return ok


def test_lab():
    assert check(LAB, L)


def test_box_cache():
    d = pathlib.Path(tempfile.mkdtemp())
    calls = []
    game = {"gameStatus": 3, "homeTeam": {"teamTricode": "PHI", "players": [{"personId": 7, "name": "A"}]},
            "awayTeam": {"teamTricode": "DET", "players": []}}
    get = lambda g: calls.append(g) or game
    first = LAB.final_box("G", get, cache=d / "c.sqlite")
    again = LAB.final_box("G", get, cache=d / "c.sqlite")
    assert first[7]["_team"] == "PHI" and again == first and calls == ["G"]
    live = dict(game, gameStatus=2)
    assert LAB.final_box("H", lambda g: live, cache=d / "c.sqlite") is None      # not final: not cached


def test_mutants():
    for mod, tag, a, b in (
            (LAB, "beat direction", "beat = close[0] > line0 or", "beat = close[0] < line0 or"),
            (LAB, "premise inverted", 'return "played" if p.get("played") == "1" else "sat"',
             'return "sat" if p.get("played") == "1" else "played"'),
            (L, "game lines every cycle", "        if last == (line, odds):\n            continue\n", ""),
            (L, "sides unmapped", 'side = ("home" if rk == _nick_key(g["home_nick"])', 'side = ("x" if False')):
        src = pathlib.Path(mod.__file__).read_text()
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        name = pathlib.Path(mod.__file__).stem + "_mut25"
        (d / f"{name}.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            m = importlib.import_module(name)
            assert not check(m if mod is LAB else LAB, m if mod is L else L), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop(name, None)


if __name__ == "__main__":
    test_lab(); test_box_cache(); test_mutants()
    print("test_nba_lab: OK")
