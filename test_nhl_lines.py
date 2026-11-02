"""nhl_lines: FanDuel / DraftKings NHL market parsing (by marketType and by DraftKings category), the cycle (nfl_lines'
own, with the NHL's League), identity scoped to the game's two rosters with the NHL search for a call-up, the snapshot,
and the DraftKings receiver's NHL file. MUTANTS in test_mutants()."""
import datetime as dt
import importlib.util
import json
import pathlib
import sqlite3
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nba_dk_receive as K
import nhl_common as C
import nhl_lines as N

NOW = dt.datetime(2026, 11, 1, 18, 0, tzinfo=dt.timezone.utc)


def fdm(name, runners, mtype):
    return {"marketName": name, "marketType": mtype,
            "runners": [{"runnerName": n, "handicap": h, "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": a}}}
                        for n, h, a in runners]}


def sched():
    g = lambda gid, a, h, utc: {"gid": gid, "season": 2026, "type": "R", "away": a, "home": h, "utc": utc,
                                "home_score": None, "away_score": None, "date": utc[:10], "state": "pregame"}
    return [g("2026020230", "EDM", "NYR", "2026-11-01T23:00:00"), g("2026020231", "OTT", "ANA", "2026-11-02T01:00:00"),
            dict(g("2026020100", "EDM", "NYR", "2026-10-20T23:00:00"), home_score=2, away_score=3, state="final")]


def roster():
    r = lambda name, team, pos="C": {"name": name, "team": team, "pos": pos}
    return {8478402: r("Connor McDavid", "EDM"), 8477934: r("Leon Draisaitl", "EDM"), 8476468: r("J.T. Miller", "NYR"),
            8482116: r("Tim Stützle", "OTT"), 8476999: r("Matt Tomkins", "EDM", "G"),
            1: r("Sebastian Aho", "CAR", "C"), 2: r("Sebastian Aho", "NYI", "D"),       # the same name on two teams
            3: r("Alex Smith", "EDM", "L"), 4: r("Alex Smith", "NYR", "D")}             # ambiguous inside the game


# ── FanDuel ─────────────────────────────────────────────────────────────────────────────────────────────
def check_fd(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    x = mod.fd_extract
    want(x(fdm("Connor McDavid Shots on Goal", [("Connor McDavid - Over", 3.5, -140), ("Connor McDavid - Under", 3.5, 110)],
               "PLAYER_TOTAL_SHOTS"))
         == [("Connor McDavid", "shots", 3.5, "over", round(1 + 100 / 140, 4)), ("Connor McDavid", "shots", 3.5, "under", 2.1)],
         "two-sided O/U at the posted line, the player from the market's name")
    want([r[:4] for r in x(fdm("Matt Tomkins Alt Saves", [("24+", 0, 106), ("27+", 0, 235)], "PLAYER_ALT_SAVES"))]
         == [("Matt Tomkins", "saves", 23.5, "over"), ("Matt Tomkins", "saves", 26.5, "over")], "an alt ladder: N+ is an over at N - 0.5")
    want([r[:4] for r in x(fdm("3+ Shots on Goal", [("Leon Draisaitl", 0, -168), ("Connor McDavid", 0, -140)],
                               "PLAYER_TO_RECORD_3+_SHOTS_ON_GOAL"))]
         == [("Leon Draisaitl", "shots", 2.5, "over"), ("Connor McDavid", "shots", 2.5, "over")], "a ladder rung of players")
    want([r[1:4] for r in x(fdm("2+ Points", [("Connor McDavid", 0, -118)], "PLAYER_TO_RECORD_2+_POINTS"))] == [("points", 1.5, "over")]
         and [r[1:4] for r in x(fdm("1+ Assists", [("Adam Fox", 0, -150)], "PLAYER_TO_RECORD_1+_ASSISTS"))] == [("assists", 0.5, "over")],
         "points and assists rungs")
    want([r[1:4] for r in x(fdm("Anytime Goal Scorer", [("Leon Draisaitl", 0, 100)], "ANY_TIME_GOAL_SCORER"))] == [("goals", 0.5, "over")]
         and [r[1:4] for r in x(fdm("Player to Score 2+ Goals", [("Leon Draisaitl", 0, 600)], "PLAYER_TO_SCORE_2+_GOALS"))] == [("goals", 1.5, "over")],
         "the anytime scorer is goals over 0.5, 2+ goals over 1.5")
    want(not x(fdm("1st Period Any Time Goal Scorer", [("Leon Draisaitl", 0, 400)], "1ST_PERIOD_ANY_TIME_GOAL_SCORER"))
         and not x(fdm("First Goal Scorer", [("Leon Draisaitl", 0, 700)], "FIRST_GOAL_SCORER"))
         and not x(fdm("2nd Period Player 2+ Shots on Goal", [("Leon Draisaitl", 0, 200)], "2ND_PERIOD_PLAYER_2+_SHOTS_ON_GOAL"))
         and not x(fdm("Any Time Goal Scorer / Team to Win Parlay", [("Leon Draisaitl", 0, 250)], "PLAYER_TO_SCORE_1+_GOALS_/_TEAM_TO_WIN"))
         and not x(fdm("Player 1+ Point Each Period (60 Min)", [("Connor McDavid", 0, 900)], "PLAYER_1+_POINT_EACH_PERIOD_(60_MIN)"))
         and not x(fdm("Game to Reach Overtime & OT Goal Scorer", [("Connor McDavid", 0, 900)], "OVERTIME_GOAL_SCORER"))
         and not x(fdm("Total Goals", [("Over", 6.5, -110)], "TOTAL_POINTS_(OVER/UNDER)")),
         "periods, first scorers, parlays, each-period, overtime and game totals are left out")
    want(not x(fdm("Edmonton Oilers Shots on Goal", [("Over", 30.5, -110)], "TEAM_TOTAL_SHOTS"))
         and not x(fdm("Connor McDavid", [("Connor McDavid - Over", 3.5, -140)], "PLAYER_TOTAL_SHOTS")),
         "a team's shots are not a player's, and a market name without its stat is not read")
    return ok


def test_fd_extract():
    assert check_fd(N)


# ── DraftKings ──────────────────────────────────────────────────────────────────────────────────────────
def dkj(key, sels):
    """sels: (market name, label, points, player, decimal odds, eventId)."""
    mk, out = {}, []
    for i, (mn, label, pts, player, odds, eid) in enumerate(sels):
        mk.setdefault((mn, eid), {"id": f"m{len(mk)}", "name": mn, "eventId": eid})
        out.append({"marketId": mk[(mn, eid)]["id"], "label": label, "points": pts,
                    "participants": [{"name": player, "type": "Player"}], "displayOdds": {"decimal": str(odds)}})
    return {"_key": list(key), "markets": list(mk.values()), "selections": out}


def check_dk(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    ev = {"e1": "EDM Oilers @ NY Rangers"}
    r = mod.dk_rows(dkj((1189, "shots on goal o/u"), [("Connor McDavid Shots on Goal O/U", "Over", 3.5, "Connor McDavid", 1.8, "e1"),
                                                      ("Connor McDavid Shots on Goal O/U", "Under", 3.5, "Connor McDavid", 2.0, "e1"),
                                                      ("Mika Zibanejad Shots on Goal O/U", "Over", 2.5, "Mika Zibanejad", 1.9, "e9")]), ev)
    want([x[1:5] for x in r] == [("Connor McDavid", "shots", 3.5, "over"), ("Connor McDavid", "shots", 3.5, "under")],
         "O/U rungs, games not on the list left out")
    r = mod.dk_rows(dkj((1189, "shots on goal"), [("Adam Fox Shots on Goal", "2+", None, "Adam Fox", 1.6, "e1")]), ev)
    want([x[1:5] for x in r] == [("Adam Fox", "shots", 1.5, "over")], "a milestone N+ is an over at N - 0.5")
    r = mod.dk_rows(dkj((1190, "anytime goalscorer"), [("Anytime Goalscorer", "Leon Draisaitl", None, "Leon Draisaitl", 2.0, "e1")]), ev)
    want([x[1:5] for x in r] == [("Leon Draisaitl", "goals", 0.5, "over")], "the anytime goalscorer: goals over 0.5")
    r = mod.dk_rows(dkj((550, "power play points"), [("Connor McDavid Powerplay Points", "1+", None, "Connor McDavid", 2.1, "e1")]), ev)
    want([x[1:5] for x in r] == [("Connor McDavid", "ppp", 0.5, "over")], "power-play points")
    want(not mod.dk_rows(dkj((1899, "shots on goal"), [("Game Leader", "Connor McDavid", None, "Connor McDavid", 3.0, "e1")]), ev)
         and not mod.dk_rows(dkj((559, "shots on goal"), [("Shots", "Over", 60.5, "EDM Oilers", 1.9, "e1")]), ev)
         and not mod.dk_rows(dkj((1828, "points"), [("Connor McDavid Points", "Over", 0.5, "Connor McDavid", 1.4, "e1")]), ev),
         "the same name in another category (Game Leaders, Live Props, Live Points) is not a full-game player prop")
    return ok


def test_dk_rows():
    assert check_dk(N)


# ── the cycle and identity ──────────────────────────────────────────────────────────────────────────────
def run_cycle(db, fd_rows, dk=None, now=NOW, search=None):
    fetch = {"fd": lambda: (fd_rows, ""), "dk": dk or (lambda: ([], ""))}
    old = C.Resolver.__init__.__defaults__
    C.Resolver.__init__.__defaults__ = (search is not None, search)    # the search: off, or a fake
    try:
        return N.cycle(("fd", "dk") if dk else ("fd",), now=now, sched=sched(), roster=roster(), fetchers=fetch, db=db)
    finally:
        C.Resolver.__init__.__defaults__ = old


def test_cycle():
    db = pathlib.Path(tempfile.mkdtemp()) / "l.sqlite"
    E, O = "Edmonton Oilers @ New York Rangers", "Ottawa Senators @ Anaheim Ducks"
    rows = [(E, "Connor McDavid", "shots", 3.5, "over", 1.71), (E, "Connor McDavid", "shots", 3.5, "under", 2.1),
            (E, "Connor McDavid", "shots", 3.5, "over", 1.75),         # the same rung at two prices: the better one
            (E, "J.T. Miller", "points", 0.5, "over", 1.8), (E, "Alex Smith", "goals", 0.5, "over", 5.0),
            (E, "Edmonton Oilers", "goals", 3.5, "over", 1.9),         # a team, not a player
            (O, "Tim Stutzle", "goals", 0.5, "over", 2.45),            # no umlaut at the book
            (O, "Sebastian Aho", "points", 0.5, "over", 2.0),          # neither Aho plays in this game
            ("Boston Bruins @ Vegas Golden Knights", "X", "shots", 2.5, "over", 1.9),   # no such game
            (E, "Connor McDavid", "hits", 1.5, "over", 1.9)]           # not an NHL stat key here
    assert run_cycle(db, rows) == []
    con = sqlite3.connect(db)
    b = {(r[0], r[1], r[2], r[3]): r[4:] for r in con.execute("SELECT player, stat, line, side, pid, gid, odds FROM board")}
    assert b[("Connor McDavid", "shots", 3.5, "over")] == (8478402, "2026020230", 1.75), "one price per rung: the better one"
    assert b[("J.T. Miller", "points", 0.5, "over")][0] == 8476468, "J.T. = JT"
    assert b[("Tim Stutzle", "goals", 0.5, "over")][:2] == (8482116, "2026020231"), "accents folded"
    assert b[("Alex Smith", "goals", 0.5, "over")][0] is None, "an ambiguous name stays unresolved"
    assert b[("Sebastian Aho", "points", 0.5, "over")][0] is None, "a name only on other teams is not resolved"
    assert not any(k[0] == "Edmonton Oilers" for k in b) and not any(k[1] == "hits" for k in b)
    assert con.execute("SELECT status, rows, events, matched_events FROM cycles").fetchone() == ("ok", 6, 3, 2)
    # after the start nothing more is written for the game under way
    run_cycle(db, rows, now=NOW.replace(hour=23, minute=30))
    assert not con.execute("SELECT COUNT(*) FROM board WHERE gid='2026020230'").fetchone()[0]


def test_search_fallback():
    """A call-up the roster lists do not show yet: the NHL search, accepted only on one of the game's two teams."""
    C.CACHE = pathlib.Path(tempfile.mkdtemp())
    calls = []

    def search(url):
        calls.append(url)
        if "Brossoit" in url:
            return [{"playerId": "8476316", "name": "Laurent Brossoit", "teamAbbrev": "ANA"}]
        if "Smith" in url:
            return [{"playerId": "9", "name": "Jordan Smith", "teamAbbrev": "OTT"}]   # another name: not him
        return [{"playerId": "7", "name": "Joe Nobody", "teamAbbrev": "BOS"}]
    db = pathlib.Path(tempfile.mkdtemp()) / "l.sqlite"
    O = "Ottawa Senators @ Anaheim Ducks"
    run_cycle(db, [(O, "Laurent Brossoit", "saves", 25.5, "over", 1.9), (O, "Joe Nobody", "shots", 1.5, "over", 1.9),
                   (O, "Alex Smith", "shots", 1.5, "over", 1.9)], search=search)
    con = sqlite3.connect(db)
    b = {r[0]: r[1] for r in con.execute("SELECT player, pid FROM board")}
    assert b == {"Laurent Brossoit": 8476316, "Joe Nobody": None, "Alex Smith": None}, b
    n = len(calls)
    run_cycle(db, [(O, "Laurent Brossoit", "saves", 25.5, "over", 1.9)], now=NOW + dt.timedelta(minutes=5), search=search)
    assert len(calls) == n, "a search is cached, not asked again every cycle"


def check_search(mod):
    mod.CACHE = pathlib.Path(tempfile.mkdtemp())

    def search(url):
        if "Brossoit" in url:
            return [{"playerId": "8476316", "name": "Laurent Brossoit", "teamAbbrev": "ANA"}]
        if "Smith" in url:
            return [{"playerId": "9", "name": "Jordan Smith", "teamAbbrev": "OTT"}]
        return [{"playerId": "7", "name": "Joe Nobody", "teamAbbrev": "BOS"}]
    r = mod.Resolver(roster(), True, search)
    got = [r.resolve(n, ("OTT", "ANA")) for n in ("Laurent Brossoit", "Joe Nobody", "Alex Smith")]
    ok = got == [8476316, None, None]
    print(f"   {'ok ' if ok else 'BAD'} the search: his name, on one of the game's two teams ({got})")
    return ok


def test_snapshot():
    d = pathlib.Path(tempfile.mkdtemp())
    p = d / "nhl_dk_snapshot.json"
    at = (NOW - dt.timedelta(minutes=2)).replace(tzinfo=None, microsecond=0).isoformat()
    p.write_text(json.dumps({"book": "dk", "league": "nfl", "fetched_at": at, "rows": [], "detail": ""}))
    try:
        N.fetch_dk_snapshot(p, now=NOW.replace(tzinfo=None))
        assert False, "an NFL snapshot is never read as NHL"
    except N.Stale:
        pass
    row = ["EDM Oilers @ NY Rangers", "Connor McDavid", "shots", 3.5, "over", 1.8]
    p.write_text(json.dumps({"book": "dk", "league": "nhl", "fetched_at": at, "rows": [row], "detail": ""}))
    db = d / "l.sqlite"
    run_cycle(db, [], dk=lambda: N.fetch_dk_snapshot(p, now=NOW.replace(tzinfo=None)))
    con = sqlite3.connect(db)
    assert con.execute("SELECT collected_at, pid FROM board WHERE book='dk'").fetchall() == [(at, 8478402)]


def check_recv(mod):
    RNOW = dt.datetime(2026, 11, 1, 18, 0, 0)

    def snap(league):
        s = {"book": "dk", "fetched_at": (RNOW - dt.timedelta(seconds=30)).isoformat(), "detail": "",
             "rows": [["EDM Oilers @ NY Rangers", "Connor McDavid", "shots", 3.5, "over", 1.8]]}
        if league:
            s["league"] = league
        return json.dumps(s).encode()
    d = pathlib.Path(tempfile.mkdtemp())
    nba, nfl, nhl = d / "dk_snapshot.json", d / "nfl_dk_snapshot.json", d / "nhl_dk_snapshot.json"
    code, _ = mod.receive(snap("nhl"), RNOW, nba, nfl, nhl)
    ok = code == 0 and nhl.exists() and not nba.exists() and not nfl.exists() and json.loads(nhl.read_text())["league"] == "nhl"
    print(f"   {'ok ' if ok else 'BAD'} an NHL snapshot goes to its own file")
    return ok


def test_receiver_nhl():
    assert check_recv(K)


def _mutant(path, name, old, new):
    src = pathlib.Path(path).read_text()
    assert src.count(old) == 1, (name, old)
    d = pathlib.Path(tempfile.mkdtemp())
    f = d / f"{name}.py"
    f.write_text(src.replace(old, new))
    sys.path.insert(0, str(d))
    try:
        spec = importlib.util.spec_from_file_location(name, f)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        sys.path.remove(str(d))


def test_mutants():
    """Every guard above fails its check when broken."""
    cases = [
        (C.__file__, "nhl_common_m1", "hits = {p for p, t in self._found(name) if t in teams}", "hits = {p for p, t in self._found(name) if t}",
         check_search, "a search hit on another team"),
        (C.__file__, "nhl_common_m2", "if nosfx(fold(r.get(\"name\"))) == k and r.get(\"playerId\")]]", "if r.get(\"playerId\")]]",
         check_search, "a search hit of another name"),
        (N.__file__, "nhl_lines_m3", "return each_player(stat, int(mm.group(1)) - 0.5) if stat else []",
         "return each_player(stat, int(mm.group(1))) if stat else []", check_fd, "N+ is N - 0.5"),
        (N.__file__, "nhl_lines_m4", "if not stat or not player or player == nm:", "if not stat or not player:", check_fd, "a team's shots"),
        (N.__file__, "nhl_lines_m5", '(1675, "points o/u"): "points", (1675, "points"): "points",', '(1675, "points o/u"): "points", (1828, "points"): "points",',
         check_dk, "category pinned"),
        (N.__file__, "nhl_lines_m6", "side, pts = \"over\", float(raw[:-1]) - 0.5", "side, pts = \"over\", float(raw[:-1])", check_dk, "milestone"),
        (K.__file__, "nba_dk_receive_m9", 'out, tag = out_nhl, "nhl "', 'out, tag = out_nfl, "nhl "', check_recv, "receiver dispatch"),
    ]
    for path, name, old, new, check, label in cases:
        assert not check(_mutant(path, name, old, new)), f"mutant survived: {label}"
