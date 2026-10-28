"""The Pickz NBA prop research feed (nba_research.py) and page (nba_research_ui.py): derived statistics, the payload
built from synthetic stores (books + alternate rungs, logs, official report vs news, absences, related props, live
and postponed games, stale books, engine flags), the page's JS against the Python, and the page's script syntax."""
import datetime as dt
import inspect
import json
import math
import pathlib
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_matchup as MU
import nba_research as RS
import nba_research_ui as UI

NODE = shutil.which("node")
NOW = dt.datetime(2026, 10, 26, 23, 30, tzinfo=dt.timezone.utc)      # 5:30 PM MT, 7:30 PM ET on 10/26


def test_hit_summary_and_values():
    s = RS.hit_summary([10, 12, 12, 15, None, 9], 12)
    assert s == {"n": 5, "over": 1, "under": 2, "push": 2, "avg": 11.6, "med": 12.0}
    assert RS.hit_summary([], 10.5)["n"] == 0 and RS.hit_summary([None], 10.5)["avg"] is None
    lg = {"pts": 20, "reb": 5, "ast": 7, "fg3m": None}
    assert RS.stat_value(lg, "pra") == 32 and RS.stat_value(lg, "pts_ast") == 27 and RS.stat_value(lg, "threes") is None


def test_pearson_and_main_line():
    assert RS.pearson([1, 2, 3, None, 4], [2, 4, 6, 100, 8]) == pytest.approx(1.0)      # the None pair is dropped
    assert RS.pearson([1, 2], [1, 2]) is None and RS.pearson([1, 1, 1], [1, 2, 3]) is None
    assert RS.pearson([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    rungs = [[4.5, 1.04, None], [11.5, 1.77, 1.98], [12.5, 2.05, 1.75], [19.5, 7.0, None]]
    assert RS.main_line(rungs) == 11.5 and RS.main_line([[4.5, 1.04, None]]) is None


# ── a synthetic slate ─────────────────────────────────────────────────────────────────────────────────────
GD = "2026-10-26"
SCHED = [{"gid": "G1", "date_et": GD, "utc": "2026-10-27T00:00:00Z", "status": 2, "status_text": "Q3 4:12",
          "home": "PHX", "away": "SAC"},
         {"gid": "G2", "date_et": GD, "utc": "2026-10-27T02:00:00Z", "status": 1, "status_text": "PPD",
          "home": "LAL", "away": "DEN"},
         {"gid": "G3", "date_et": "2026-10-27", "utc": "2026-10-28T00:00:00Z", "status": 1, "status_text": "7:00 pm ET",
          "home": "BOS", "away": "NYK"},
         {"gid": "G9", "date_et": "2026-10-30", "utc": "2026-10-31T00:00:00Z", "status": 1, "status_text": "",
          "home": "MIA", "away": "ORL"}]          # outside today/tomorrow: not on the page


def stores(d):
    q = sqlite3.connect(d / "lines.sqlite")
    q.execute("CREATE TABLE board (book TEXT, collected_at TEXT, gid TEXT, tip_utc TEXT, event TEXT, home TEXT, away TEXT, "
              "pid INTEGER, player TEXT, stat TEXT, line REAL, side TEXT, odds REAL)")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT, stat TEXT, "
              "line REAL, side TEXT, odds REAL)")
    q.execute("CREATE TABLE game_lines (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, market TEXT, side TEXT, line REAL, "
              "odds REAL)")
    rows = [("fd", "2026-10-26T23:25:00", "G1", 1, "Devin Booker", "points", 24.5, "over", 1.87),
            ("fd", "2026-10-26T23:25:00", "G1", 1, "Devin Booker", "points", 24.5, "under", 1.95),
            ("fd", "2026-10-26T23:25:00", "G1", 1, "Devin Booker", "points", 29.5, "over", 3.2),       # alt, over only
            ("dk", "2026-10-26T22:50:00", "G1", 1, "Devin Booker", "points", 25.5, "over", 1.95),      # DK: other line
            ("dk", "2026-10-26T22:50:00", "G1", 1, "Devin Booker", "points", 25.5, "under", 1.87),
            ("fd", "2026-10-26T23:25:00", "G1", 1, "Devin Booker", "assists", 6.5, "over", 1.9),
            ("fd", "2026-10-26T23:25:00", "G1", 1, "Devin Booker", "assists", 6.5, "under", 1.9),
            ("fd", "2026-10-26T23:25:00", "G1", 2, "Grayson Allen", "points", 11.5, "over", 1.9),
            ("fd", "2026-10-26T23:25:00", "G1", 2, "Grayson Allen", "points", 11.5, "under", 1.9),
            ("fd", "2026-10-26T23:25:00", "G1", 7, "Mystery Man", "steals", 1.5, "over", 1.9),         # unsupported
            ("fd", "2026-10-26T23:25:00", "G9", 9, "Not Today", "points", 10.5, "over", 1.9)]
    q.executemany("INSERT INTO board VALUES (?,?,?,'', '', '', '', ?,?,?,?,?,?)",
                  [(b, at, g, p, n, s, ln, sd, o) for b, at, g, p, n, s, ln, sd, o in rows])
    for t, line, o in (("2026-10-26T15:00:00", 23.5, 1.9), ("2026-10-26T20:00:00", 24.5, 1.87)):
        for side, oo in (("over", o), ("under", 1.9)):
            q.execute("INSERT INTO quotes VALUES (?, 'fd', 'G1', '', 1, 'Devin Booker', 'points', ?, ?, ?)", (t, line, side, oo))
    for market, side, line in (("spread", "home", -5.5), ("spread", "away", 5.5), ("total", "over", 228.5)):
        q.execute("INSERT INTO game_lines VALUES ('2026-10-26T23:00:00', 'fd', 'G1', '', ?, ?, ?, 1.9)", (market, side, line))
    q.commit(); q.close()
    n = sqlite3.connect(d / "news.sqlite")
    n.execute("CREATE TABLE snapshots (mark TEXT, published_at TEXT, game_date TEXT, matchup TEXT, team TEXT, pid INTEGER, "
              "player TEXT, status TEXT, reason TEXT)")
    n.execute("CREATE TABLE news_items (source TEXT, item_id TEXT, detected_at TEXT, player TEXT, pid INTEGER, team TEXT, "
              "game_date TEXT, status TEXT, headline TEXT, body TEXT, provenance TEXT, seeded INTEGER)")
    old = ("2026-10-26T13:00", "2026-10-26T17:00:04+00:00")
    new = ("2026-10-26T17:30", "2026-10-26T21:30:04+00:00")
    n.executemany("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)", [
        (*old, GD, "SAC@PHX", "PHX", 2, "Grayson Allen", "Questionable", "Injury/Illness - Ankle"),
        (*new, GD, "SAC@PHX", "PHX", 3, "Jusuf Nurkic", "Out", "Injury/Illness - Knee 07:30 (ET)"),  # parser's time column     # Allen dropped off: cleared
        (*new, GD, "SAC@PHX", "PHX", 8, "Former Sun", "Out", "Rest")])                      # traded: SAC logs only
    n.execute("INSERT INTO news_items VALUES ('x','i1','2026-10-26T20:00:00+00:00','Devin Booker',1,'PHX',?, 'q',"
              "'Booker questionable (ankle)','','x:underdog',0)", (GD,))
    n.commit(); n.close()
    sh = sqlite3.connect(d / "shadow.sqlite")
    sh.execute("CREATE TABLE flags (flag_id TEXT, logged_at TEXT, game_date TEXT, gid TEXT, pid INTEGER, stat TEXT, tier TEXT, "
               "card INTEGER, card_why TEXT, line REAL, void_reason TEXT)")
    sh.execute("INSERT INTO flags VALUES ('f','2026-10-26T20:00:00',?, 'G1', 2, 'pts', 'wowy', 0, 'EDGE TOO BIG', 11.5, NULL)", (GD,))
    sh.commit(); sh.close()
    m = MU.connect(d / "matchup.sqlite")
    rnd = random.Random(3)
    PG = "INSERT INTO player_games (gid, team, pid, pos, starter, min, pts, reb, ast, fg3m, stl, blk, tov, fga, fg3a, fta) " \
         "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    day = dt.date(2026, 9, 1)
    for i in range(30):                                  # 30 PHX games this season; Nurkic sits in games 20-29
        gid, date = f"0022600{i:03d}", day.isoformat()
        day += dt.timedelta(days=1 + i % 3)              # rest 0, 1, 2 days in turn (0 = back-to-back)
        home = "PHX" if i % 2 else "UTA"                 # PHX wins the even games by 8, loses the odd ones by 5
        phx, uta = (110, 102) if i % 2 == 0 else (100, 105)
        m.execute("INSERT INTO games (gid, season, date, home, away, home_pts, away_pts) VALUES (?,?,?,?,?,?,?)",
                  (gid, "2026-27", date, home, "UTA" if home == "PHX" else "PHX", phx if home == "PHX" else uta,
                   uta if home == "PHX" else phx))
        for t in ("PHX", "UTA"):
            m.execute("INSERT INTO team_games VALUES (?,?,?,90,20,10,12)", (gid, t, "UTA" if t == "PHX" else "PHX"))
        b_pts = 20 + i % 10
        m.execute(PG, (gid, "PHX", 1, "SG", 1, 30 + i % 10, b_pts, 4, 6 + (i % 3), 3, 1, 0, 3, 15 + i % 10, 6 + i % 4, 4 + i % 5))
        m.execute(PG, (gid, "PHX", 2, "", 0, 26, 10 + rnd.randint(-3, 3), 3, 2, 2, 1, 0, 1, 9, 4, 2))
        if i < 20:
            m.execute(PG, (gid, "PHX", 3, "C", 1, 28, 12, 10, 3, 0, 1, 1, 2, 10, 0, 4))
            m.execute(PG, (gid, "SAC", 8, "PF", 1, 30, 15, 6, 2, 1, 1, 0, 1, 12, 3, 3))   # a SAC history: not PHX's absence
    m.commit(); m.close()
    (d / "index.json").write_text(json.dumps({"players": {"1": ["PHX", "Devin Booker", "G"], "2": ["PHX", "Grayson Allen", "G"],
                                                           "3": ["PHX", "Jusuf Nurkic", "C"], "8": ["PHX", "Former Sun", "F"]}}))


def live_box(gid):
    assert gid == "G1"                                   # only the live game is fetched (G2 is postponed)
    mk = lambda pid, pts, ast: {"personId": pid, "played": "1", "statistics": {"minutes": "PT24M30.00S", "points": pts,
                                "reboundsTotal": 2, "assists": ast, "threePointersMade": 1}}
    return {"gameStatus": 2, "gameStatusText": "Q3 4:12", "homeTeam": {"score": 70, "players": [mk(1, 18, 4), mk(2, 7, 1)]},
            "awayTeam": {"score": 66, "players": []}}


def built(now, sched=None, box_get=None):
    d = pathlib.Path(tempfile.mkdtemp())
    stores(d)
    tr = sqlite3.connect(d / "tracking.sqlite")
    tr.execute("CREATE TABLE tracking (date TEXT, player_id INTEGER, potential_ast REAL, ast_trk REAL, passes REAL, "
               "secondary_ast REAL, ft_ast REAL, reb_chances REAL, oreb_chances REAL, dreb_chances REAL, reb_trk REAL)")
    tr.execute("INSERT INTO tracking (date, player_id, potential_ast, reb_chances) VALUES ('2026-09-01', 1, 14, 9)")
    tr.execute("INSERT INTO tracking (date, player_id, potential_ast, reb_chances) VALUES ('2026-09-02', 1, 11, NULL)")
    tr.commit(); tr.close()
    rl = sqlite3.connect(d / "role.sqlite")              # the engine's flags (nba_role.sqlite), as nba_role_open.py writes them
    rl.execute("CREATE TABLE ratio_signals (rule TEXT, gid TEXT, pid INTEGER, market TEXT, book TEXT, line REAL, price REAL, "
               "volume REAL, date TEXT, player TEXT, logged_at TEXT, pinged INTEGER, PRIMARY KEY (rule, gid, pid, market))")
    rl.execute("CREATE TABLE idea_signals (rule TEXT, gid TEXT, pid INTEGER, market TEXT, line REAL, price REAL, note TEXT, "
               "date TEXT, player TEXT, logged_at TEXT, pinged INTEGER, PRIMARY KEY (rule, gid, pid, market))")
    rl.execute("CREATE TABLE signals (gid TEXT, pid INTEGER, market TEXT, side TEXT, book TEXT, line REAL, price REAL, ev REAL, "
               "p REAL, mu REAL, out_pids TEXT, date TEXT, team TEXT, player TEXT, logged_at TEXT, pinged INTEGER, "
               "PRIMARY KEY (gid, pid, market, side))")
    rl.executemany("INSERT INTO ratio_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
        ("EARLY_SURGE", "G1", 1, "points", "fd", 24.5, 1.87, 18.0, GD, "Devin Booker", "2026-10-26T02:00:00", 1),
        ("RATIO_PA28", "G0", 1, "assists", "fd", 5.5, 1.9, 10.0, "2026-10-20", "Devin Booker", "2026-10-20T02:00:00", 1)])
    rl.executemany("INSERT INTO idea_signals VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
        ("UNDERML", "G1", 2, "points", 9.5, 1.9259, "under p 0.443 ev 0.073", GD, "Grayson Allen", "2026-10-26T23:30:00", 0),
        ("UNDER20", "G1", 2, "rebounds", 3.5, 1.8, "proj 2.1 min 19.8", GD, "Grayson Allen", "2026-10-26T23:30:01", 0),  # a failed send
        ("UNDER20", "G1", 1, "points", 24.5, 1.7, "proj 15.9 min 30.2", GD, "Devin Booker", "2026-10-26T23:30:00", 1),
        ("UNDER20", "G1", 1, "rebounds", 5.5, 1.7, "proj 3.9 min 30.2", GD, "Devin Booker", "2026-10-26T23:30:00", 0),   # 29% below
        ("UNDER20", "G1", 1, "assists", 6.5, 1.6, "proj 3.5 min 30.2", GD, "Devin Booker", "2026-10-26T23:30:00", 0),    # −167
        ("UNDER20", "G1", 1, "threes", 2.5, 1.9, "proj 1.5 min 30.2", GD, "Devin Booker", "2026-10-26T23:30:00", 0),     # threes
        ("RETURN_UNDER", "G1", 2, "assists", 3.5, 1.8, "proj 2.0 min 18.0", GD, "Grayson Allen", "2026-10-26T23:30:00", 1),  # another rule
        ("UNDER20", "G0", 1, "points", 24.5, 1.7, "proj 15.0 min 30.2", "2026-10-20", "Devin Booker", "2026-10-20T23:30:00", 1)])
    rl.execute("INSERT INTO signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               ("G1", 3, "rebounds", "under", "fd", 9.5, 2.0, 0.109, 0.55, 7.8, "[]", GD, "PHX", "Jusuf Nurkic", "2026-10-26T06:24:03", 1))
    rl.commit(); rl.close()
    return RS.build(now=now, sched=sched or SCHED, lines=d / "lines.sqlite", news=d / "news.sqlite", shadow=d / "shadow.sqlite",
                    matchup=d / "matchup.sqlite", index=d / "index.json", box_get=box_get or live_box, tracking=d / "tracking.sqlite",
                    role_db=d / "role.sqlite")


@pytest.fixture(scope="module")
def payload():
    return built(NOW)


def _corr_reference(props, logs):
    """correlations as first written (every pair both ways, five-pass Pearson): the fast one must match it exactly."""
    def pearson(xs, ys):
        pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
        if len(pairs) < 3:
            return None
        mx = sum(x for x, _ in pairs) / len(pairs)
        my = sum(y for _, y in pairs) / len(pairs)
        sxy = sum((x - mx) * (y - my) for x, y in pairs)
        sxx = sum((x - mx) ** 2 for x, _ in pairs)
        syy = sum((y - my) ** 2 for _, y in pairs)
        return None if sxx <= 0 or syy <= 0 else sxy / math.sqrt(sxx * syy)
    series = {p["id"]: {r[1]: (r[2], RS.stat_value(dict(zip(RS.LOG_COLS, r)), p["market"])) for r in logs.get(p["pid"], [])} for p in props}
    out = {}
    for p in props:
        mine, res = series[p["id"]], []
        for o in props:
            if o["gid"] != p["gid"] or o["id"] == p["id"] or (o["pid"] == p["pid"] and o["market"] == p["market"]):
                continue
            if o["pid"] != p["pid"] and o["team"] != p["team"]:
                continue
            theirs = series[o["id"]]
            shared = [g for g in mine.keys() & theirs.keys() if mine[g][0] == theirs[g][0] == p["team"]]
            if len(shared) < RS.CORR_MIN_N:
                continue
            r = pearson([mine[g][1] for g in shared], [theirs[g][1] for g in shared])
            if r is not None:
                res.append({"id": o["id"], "r": round(r, 2), "n": len(shared)})
        out[p["id"]] = sorted(res, key=lambda x: (-abs(x["r"]), x["id"]))[:RS.CORR_TOP]
    return out


def test_correlations_match_the_reference():
    # each pair computed once now (r is symmetric): the same lists as computing both ways, on random teams and logs,
    # a player's props on two teams (one unresolved) included
    for seed in range(4):
        rnd = random.Random(seed)
        props, logs = [], {}
        for g in range(4):
            for t in ("A", "B"):
                for pid in range(g * 100 + (0 if t == "A" else 50), g * 100 + (0 if t == "A" else 50) + 6):
                    logs[pid] = [[{"date": f"2026-0{1 + k % 9}-{10 + k % 18}", "gid": f"g{k}", "team": t if rnd.random() < 0.95 else "Z",
                                   "min": 30.0, "pts": rnd.randint(0, 40), "reb": rnd.randint(0, 15), "ast": rnd.randint(0, 12),
                                   "fg3m": rnd.randint(0, 6)}.get(c) for c in RS.LOG_COLS] for k in range(40 if pid % 3 else 12)
                                  if rnd.random() < 0.8]                       # some with few games: under the minimum
                    for m in rnd.sample(["points", "rebounds", "assists", "threes", "pra", "pts_reb"], 3):
                        props.append({"id": f"G{g}|{pid}|{m}", "gid": f"G{g}", "pid": pid, "market": m, "team": t if rnd.random() < 0.95 else None})
        assert RS.correlations(props, logs) == _corr_reference(props, logs)
    assert RS.pearson([1, 2, 3, None, 4], [2, 4, 6.5, 1, 8]) == pytest.approx(0.99586, abs=1e-5) and RS.pearson([1, 1, 1], [1, 2, 3]) is None


def test_flags_are_the_under_plays(payload):
    # only the under plays that ping: UNDER20 rows at −150 or better, not threes, our projection 30–50% below the line,
    # whether or not the send went through; another date's, the other rules', and UNDER20's other rows left out
    fl = payload["flags"]
    assert [(f["pid"], f["market"], f["line"], f["proj"]) for f in fl] == [(1, "points", 24.5, 15.9), (2, "rebounds", 3.5, 2.1)]
    assert all(f["side"] == "under" and f["date"] == GD for f in fl) and fl[0]["team"] == "PHX" and fl[0]["mins"] == 30.2
    assert fl[0]["price"] == 1.7 and fl[0]["at"] == "2026-10-26T23:30:00" and fl[1]["player"] == "Grayson Allen"


def test_under_flags_reader():
    assert RS.under_flags(None, [GD]) == [] and RS.under_flags(sqlite3.connect(":memory:"), []) == []
    assert RS.under_flags(sqlite3.connect(":memory:"), [GD]) == []          # no table yet
    U = RS.under_play
    assert U("points", 1 / 0.6, 10, 6.99) and U("points", 1.6667, 10, 5.0) and not U("points", 1.66, 10, 6)   # −150 or better
    assert not U("points", 1.9, 10, 7.0) and not U("points", 1.9, 10, 4.99) and not U("threes", 1.9, 2.5, 1.5)  # 30–50% below
    assert not U("points", 1.9, 0, 0) and not U("points", None, 10, 6) and not U("pra", 1.9, 30.5, None)
    rc = sqlite3.connect(":memory:")
    rc.execute("CREATE TABLE idea_signals (rule TEXT, gid TEXT, pid INTEGER, market TEXT, line REAL, price REAL, note TEXT, "
               "date TEXT, player TEXT, logged_at TEXT, pinged INTEGER)")
    rc.execute("INSERT INTO idea_signals VALUES ('UNDER20','G1',1,'pra',30.5,1.8,'proj 18.0',?,'A','2026-10-26T23:30:00',0)", (GD,))
    rc.execute("INSERT INTO idea_signals VALUES ('UNDER20','G1',2,'pra',30.5,1.8,'no projection',?,'B','2026-10-26T23:30:00',1)", (GD,))
    assert [(f["pid"], f["proj"], f["mins"]) for f in RS.under_flags(rc, [GD])] == [(1, 18.0, None)]


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_flag_grade():
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "core.js").write_text(UI.JS_CORE)
    (d / "t.js").write_text("""const C = require('./core.js');
console.log(JSON.stringify([['over', 5.5, 6], ['over', 5.5, 5], ['under', 5.5, 5], ['under', 5.5, 6], ['over', 6, 6], ['under', 6, 6],
  ['over', 5.5, null]].map(a => C.flagGrade(a[0], a[1], a[2]))));""")
    out = json.loads(subprocess.run([NODE, str(d / "t.js")], capture_output=True, text=True, check=True, cwd=d).stdout)
    assert out == ["hit", "miss", "hit", "miss", "push", "push", None]


def test_slate_holds_until_6am_et():
    # 1:30 AM ET (11:30 PM MT): still Monday's slate, the late game and its props on it; 6:30 AM ET: Tuesday's
    late = built(NOW + dt.timedelta(hours=6))
    assert late["dates"][0] == GD and any(g["gid"] == "G1" for g in late["games"]) and late["props"]
    assert built(NOW + dt.timedelta(hours=11))["dates"][0] == "2026-10-27"


def test_payload_props_and_books(payload):
    ids = {p["id"] for p in payload["props"]}
    assert ids == {"G1|1|points", "G1|1|assists", "G1|2|points"}, ids          # no steals, no out-of-range game
    # the line history, compact: whole minutes since hist_t0, prices to 3 places (as ISO strings it was 2/3 of a prop)
    pts = [x for p in payload["props"] for h in p["hist"].values() for x in h]
    assert pts and payload["hist_t0"] and all(isinstance(x[0], int) and x[0] >= 0 for x in pts)
    assert all(x[k] is None or round(x[k], 3) == x[k] for x in pts for k in (2, 3))
    g1 = next(g for g in payload["games"] if g["gid"] == "G1")
    assert set(g1["spots"]) == {g1["home"], g1["away"]} and g1["spots"][g1["home"]]["rest"] is None   # each team's schedule spot
    b = next(p for p in payload["props"] if p["id"] == "G1|1|points")
    assert b["main"] == 24.5 and b["books"]["fd"]["main"] == 24.5 and b["books"]["dk"]["main"] == 25.5
    assert [29.5, 3.2, None] in b["books"]["fd"]["rungs"]                       # the over-only alt is kept, as such
    assert (b["team"], b["opp"], b["home"]) == ("PHX", "SAC", True)
    assert b["open"] == [23.5, 1.9, "2026-10-26T15:00:00"]
    lg = [dict(zip(RS.LOG_COLS, r)) for r in payload["players"]["1"]["logs"]]
    assert [l["rest"] for l in lg[:5]] == [None, 0, 1, 2, 0]                     # days off; none before his first game
    assert [l["margin"] for l in lg[:2]] == [8, -5] and lg[0]["fga"] == 15 and lg[0]["fta"] == 4
    # usage %: (15 FGA + .44 * 4 FTA + 3 TOV) of PHX's (90 + .44 * 20 + 12), over his 30 of the team's 84 minutes / 5
    assert lg[0]["usg"] == round(100 * (15 + .44 * 4 + 3) * (84 / 5) / (30 * (90 + .44 * 20 + 12)), 1) == 10.0
    assert RS.usage(0.5, 1, 0, 0, 90, 20, 12, 240) is None and RS.usage(30, 15, 4, 3, None, 20, 12, 240) is None
    # tracking: potential assists / rebound chances; a tracked game with no rebounding row is 0 chances; none untracked
    assert [(l["pot_ast"], l["reb_ch"]) for l in lg[:3]] == [(14, 9), (11, 0), (None, None)]
    s = b["summary"]["l10"]                                                    # last 10 PHX games: 20..29 pts
    assert s["n"] == 10 and s["over"] == 5 and s["under"] == 5
    assert payload["sources"]["books"]["dk"]["stale"] is True and payload["sources"]["books"]["fd"]["stale"] is False
    assert json.loads(json.dumps(payload, default=str))                       # serializable as written


def test_payload_games_live_and_postponed(payload):
    g = {x["gid"]: x for x in payload["games"]}
    assert set(g) == {"G1", "G2", "G3"} and g["G2"]["state"] == "postponed" and g["G3"]["state"] == "pregame"
    assert g["G1"]["state"] == "live" and g["G1"]["score"] == [66, 70] and g["G1"]["lines"]["total"] == 228.5
    b = next(p for p in payload["props"] if p["id"] == "G1|1|points")
    assert b["live"] == {"value": 18.0, "min": 24.5}


def test_payload_availability(payload):
    inj = payload["injuries"]
    assert inj[f"{GD}|2"]["official"] is None and inj[f"{GD}|2"]["listed_team"] is True    # dropped from the latest report
    assert inj[f"{GD}|1"]["news"][0]["source"] == "x @underdog" and inj[f"{GD}|1"]["official"] is None
    ab = payload["absences"][f"{GD}|PHX"]
    assert [a["pid"] for a in ab] == [3] and ab[0]["name"] == "Jusuf Nurkic" and len(ab[0]["played"]) == 20  # not the traded 8
    # the With / Without filter's data: PHX's games, and each player on its roster now who played for it, most minutes first
    mt = payload["mates"]["PHX"]
    assert len(mt["gids"]) == 30 and [m["pid"] for m in mt["mates"]] == [1, 3, 2]          # not 8: no PHX game
    nk = mt["mates"][1]
    assert nk["on"] == "1" * 20 + "0" * 10 and nk["since"] == mt["mates"][0]["since"] and nk["gp"] == 20 and nk["mpg"] == 28.0
    ir = payload["inj_report"][f"{GD}|PHX"]                # the Injuries view: the traded-in 8 has no PHX game to read
    assert ir["listed"] and [(e["pid"], e["missed"], e["starter"]) for e in ir["players"]] == [(8, 0, True), (3, 10, True)]
    assert ir["players"][1]["reason"] == "Injury/Illness - Knee" and not ir["players"][1]["fresh"]   # out the last 10


def test_payload_related_and_flags(payload):
    rel = payload["related"]["G1|1|points"]
    assert {r["id"] for r in rel} <= {"G1|1|assists", "G1|2|points"} and all(r["n"] >= 15 for r in rel)
    allen = next(p for p in payload["props"] if p["id"] == "G1|2|points")
    assert allen["flag"] == {"tier": "wowy", "card": 0, "why": "EDGE TOO BIG", "line": 11.5}
    assert allen["ctx"]["group"] is None or allen["ctx"]["group"] in ("G", "F", "C")
    b = next(p for p in payload["props"] if p["id"] == "G1|1|points")
    assert b["ctx"]["group"] == "G" and b["ctx"]["opp_games"] == 0                 # SAC has no cached games
    assert b["ctx"]["def_rank"] is None and b["ctx"]["pace_rank"] is None           # no rank without opponent games
    assert b["ctx"]["pos"] == "SG" and allen["ctx"]["pos"] == "G"                    # his starts; else the index
    assert (b["ctx"]["pos_rank"], b["ctx"]["pos_n"]) == (1, 2) and allen["ctx"]["pos_rank"] == 2   # PPG among guards
    rt = payload["ranks"][GD]
    assert rt["teams"] == 2 and sorted(rt["def"].values()) == [1, 2] and set(rt["dvp"]) == {"G", "F", "C"}
    assert sorted(rt["dvp"]["G"]["points"].values()) == [1, 2]
    assert payload["ranks"]["2025-26"]["teams"] == 0                                  # no cached games last season


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_js_matches_python(payload):
    rnd = random.Random(11)
    cases = [[rnd.choice([None] + list(range(0, 40))) for _ in range(rnd.randint(0, 25))] for _ in range(40)]
    lines = [rnd.choice([0.5, 9.5, 12, 20.5, 25]) for _ in cases]
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "core.js").write_text(UI.JS_CORE)
    p = next(x for x in payload["props"] if x["id"] == "G1|1|points")
    logs = [dict(zip(RS.LOG_COLS, r)) for r in payload["players"]["1"]["logs"]]
    (d / "t.js").write_text("""
const C = require('./core.js'); const fs = require('fs');
const inp = JSON.parse(fs.readFileSync(process.argv[2]));
const out = {hits: inp.cases.map((v, i) => C.hitSummary(v, inp.lines[i]))};
out.vals = inp.logs.map(l => [C.statValue(l, 'pra'), C.statValue(l, 'threes')]);
out.win = ['l5','l10','l20','season','last','all'].map(w => C.windowed(inp.logs, w, '2026-27').length);
out.splits = C.splitRows(inp.logs, 'points', 24.5, {opp: 'UTA', without: [{name: 'N', played: inp.played, since: '2026-09-01', team: 'PHX'}]})
  .map(r => [r.label, r.s.n, r.s.over]);
const props = inp.props, g = {G1: {date: '2026-10-26'}, G2: {date: '2026-10-26'}};
const st = {date: '2026-10-26', gid: 'all', team: 'all', market: 'points', book: 'dk', q: '', lmin: '', lmax: '', omin: '', omax: ''};
out.f1 = C.filterProps(props, st, x => g[x], () => []).map(p => p.id);
out.f2 = C.filterProps(props, Object.assign({}, st, {market: 'all', book: 'all', q: 'allen'}), x => g[x], () => []).map(p => p.id);
out.f3 = C.filterProps(props, Object.assign({}, st, {market: 'all', book: 'all', lmin: '12', omax: '-110'}), x => g[x], () => []).map(p => p.id);
out.s1 = C.sortProps(props, 'line', 'asc', () => []).map(p => p.id);
out.s2 = C.sortProps(props, 'hit10', 'desc', () => []).map(p => p.id);
out.am = [C.american(1.87), C.american(2.5), C.american(null), Math.round(C.decimalOf(-150) * 1000)];
out.fl = [C.filterLogs(inp.logs, {home: true}).length, C.filterLogs(inp.logs, {home: false, starter: true}).length,
          C.filterLogs(inp.logs, {without: [{played: inp.played, since: '2026-09-01', team: 'PHX'}]}).length,
          C.filterLogs(inp.logs, {starter: false}).length];
const book = props.find(p => p.id === 'G1|1|points');
out.rates = C.propRates(book, inp.logs, 'under', '2026-27');
const logsOf = p => p.pid === 1 ? inp.logs : [];
out.su = C.sortProps(props, 'hit10', 'desc', logsOf, 'under', '2026-27').map(p => p.id);
out.bp = [C.bestPrice(book, 24.5, 'all', 'under'), C.bestPrice(book, 25.5, 'all', 'over'), C.bestPrice(book, 29.5, 'all', 'under')];
out.fr = [C.filterLogs(inp.logs, {ranges: {min: [35, 39]}}).length, C.filterLogs(inp.logs, {result: 'W'}).length,
          C.filterLogs(inp.logs, {rest: 'b2b'}).length, C.filterLogs(inp.logs, {rest: '2+'}).length,
          C.filterLogs(inp.logs, {ranges: {fga: [20, 24]}, result: 'L', home: true}).length,
          C.filterLogs(inp.logs, {ranges: {margin: [-5, -5]}}).length,
          C.filterLogs(inp.logs, {oppSets: [{'2026-27': ['UTA']}]}).length, C.filterLogs(inp.logs, {oppSets: [{'2025-26': ['UTA']}]}).length];
out.px = inp.props.map(p => [C.fairAt(p, p.main), C.valueAt(p, p.main, 'over'), C.valueAt(p, p.main, 'under')]);
const nk = {played: inp.played, since: '2026-09-01', team: 'PHX'};
out.fw = [C.filterLogs(inp.logs, {with: [nk]}).length, C.filterLogs(inp.logs, {with: [nk], without: [nk]}).length,
          C.filterLogs(inp.logs, {with: [Object.assign({}, nk, {team: 'SAC'})]}).length,
          C.filterLogs(inp.logs, {with: [nk], home: true}).length, C.filterLogs(inp.logs, {blow: 'b'}).length];
out.z = [C.zscore(7, 10, 0.5), C.zscore(0, 0, 0.5), C.zscore(3, 3, null)];
out.sv = C.sortProps(props, 'value', 'desc', () => [], 'over').map(p => p.id);
out.lst = [[18, 20.5, true, true], [18, 20, true, true], [21, 20, true, true], [20, 20, true, false], [19, 20.5, true, false],
           [18, 20.5, false, true], [20, 20.5, false, true], [19, 20, false, true], [21, 20, false, true], [20, 20, false, false], [18, 20, false, false]]
          .map(a => C.liveStatus(a[0], a[1], a[2], a[3])[0]);
out.ls = [C.liveStage('live', 3, 1.5, true), C.liveStage('live', 1, 1.5, true), C.liveStage('final', 0, 1.5, true),
          C.liveStage('live', 20, 18.5, false), C.liveStage('live', 10, 18.5, false), C.liveStage('live', 20, 20, false)];
console.log(JSON.stringify(out));
""")
    inp = {"cases": cases, "lines": lines, "logs": logs, "props": payload["props"],
           "played": payload["absences"][f"{GD}|PHX"][0]["played"]}
    (d / "in.json").write_text(json.dumps(inp))
    out = json.loads(subprocess.run([NODE, str(d / "t.js"), str(d / "in.json")], capture_output=True, text=True,
                                    check=True, cwd=d).stdout)
    for js, v, ln in zip(out["hits"], cases, lines):
        py = RS.hit_summary(v, ln)
        assert {k: js[k] for k in ("n", "over", "under", "push")} == {k: py[k] for k in ("n", "over", "under", "push")}
        assert (js["avg"] is None and py["avg"] is None) or js["avg"] == pytest.approx(py["avg"], abs=0.006)
        assert js["med"] == py["med"]
    assert out["vals"] == [[RS.stat_value(l, "pra"), RS.stat_value(l, "threes")] for l in logs]
    assert out["win"] == [5, 10, 20, 30, 0, 30]
    sp = {r[0]: r[1:] for r in out["splits"]}
    assert sp["Home"][0] + sp["Away"][0] == 30 and sp["Started"][0] == 30 and sp["Bench"][0] == 0
    assert sp["Without N"][0] == 10                                            # Nurkic sat the last 10
    assert sp["vs UTA"][0] == 30
    assert out["f1"] == ["G1|1|points"]                                        # DK + points
    # over 20.5 / 20 at 18: 3 more either way; a whole line's final push; under 20.5 at 18: 2 can still come; at 20: none
    assert out["lst"] == ["NEEDS 3", "NEEDS 3", "HIT", "PUSH", "MISS", "2 ROOM", "NO ROOM", "NO ROOM", "BUST", "PUSH", "HIT"]
    assert out["ls"] == [1, 0, 2, 1, 0, 0]              # an under at a whole line mid-game is still in play               # Live: in play first, then settled in a game still on, then finals
    assert out["f2"] == ["G1|2|points"]                                        # search
    assert out["f3"] == ["G1|1|points"]                                        # line >= 12 and over price <= -110
    assert out["s1"] == ["G1|1|assists", "G1|2|points", "G1|1|points"]          # ascending line
    assert len(out["s2"]) == 3                                                 # no logs: all missing, stable order
    assert out["s2"] == [p["id"] for p in payload["props"]]
    assert out["am"] == ["-115", "+150", "—", 1667]
    homes = sum(1 for l in logs if l["home"] == 1)
    assert out["fl"] == [homes, 30 - homes, 10, 0]                              # home; away starters; without Nurkic; bench
    # with Nurkic: his 20; with and without him: none; with him on another team: none (the games must be that team's)
    assert out["fw"] == [20, 0, 0, sum(1 for l in logs[:20] if l["home"] == 1), 0]      # no blowout: won by 8, lost by 5
    vals = [RS.stat_value(l, "points") for l in logs]
    for w, sl in (("l5", vals[-5:]), ("l10", vals[-10:]), ("l20", vals[-20:]), ("season", vals)):
        py = RS.hit_summary(sl, 24.5)
        assert out["rates"][w]["n"] == py["n"] and out["rates"][w]["rate"] == pytest.approx(py["under"] / py["n"])
    assert out["rates"]["h2h"]["n"] == 0 and out["rates"]["h2h"]["rate"] is None       # never played SAC
    assert out["su"][0] == "G1|1|points" or out["su"][0] == "G1|1|assists"             # only pid 1 has logs
    assert set(out["su"][2:]) == {"G1|2|points"}                                       # no logs: last
    assert out["bp"][0] == {"book": "fd", "odds": 1.95} and out["bp"][1] == {"book": "dk", "odds": 1.95}
    assert out["bp"][2] is None                                                        # the over-only alt has no under
    for (fair, vo, vu), pr in zip(out["px"], payload["props"]):                      # fair price + value: JS = Python
        f, n = RS.fair_at(pr["books"], pr["main"])
        assert (fair["p"] is None and f is None) or (fair["p"] == pytest.approx(f) and fair["n"] == n)
        for js, side in ((vo, "over"), (vu, "under")):
            py = RS.value_at(pr["books"], pr["main"], side)
            assert (js is None and py is None) or (js["ev"] == pytest.approx(py["ev"]) and js["book"] == py["book"])
    assert out["z"][0] == pytest.approx(RS.zscore(7, 10, .5)) and out["z"][1] is None and out["z"][2] is None
    evs = {pr["id"]: (RS.value_at(pr["books"], pr["main"], "over") or {}).get("ev") for pr in payload["props"]}
    have = [i for i in out["sv"] if evs[i] is not None]
    assert have == sorted(have, key=lambda i: -evs[i]) and out["sv"][len(have):] == [i for i in out["sv"] if evs[i] is None]
    exp = [sum(1 for l in logs if 35 <= l["min"] <= 39), sum(1 for l in logs if (l["margin"] or 0) > 0),
           sum(1 for l in logs if l["rest"] == 0), sum(1 for l in logs if l["rest"] is not None and l["rest"] >= 2),
           sum(1 for l in logs if 20 <= l["fga"] <= 24 and (l["margin"] or 0) < 0 and l["home"] == 1),
           sum(1 for l in logs if l["margin"] == -5)]
    exp += [30, 0]                                                                  # all vs UTA this season; none last
    assert out["fr"] == exp and exp[1] == 15 and exp[5] == 15 and exp[2] == 10 and 0 < exp[4] < 15, (out["fr"], exp)


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_page_scripts_parse():
    html = UI.page()
    d = pathlib.Path(tempfile.mkdtemp())
    for i, part in enumerate(html.split("<script>")[1:]):
        js = part.split("</script>")[0]
        (d / f"s{i}.js").write_text(js)
        r = subprocess.run([NODE, "--check", str(d / f"s{i}.js")], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    assert "__" not in html.split("<style>")[0] and "__TEAM_ID__" not in html and "1610612756" in html


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_rebound_rings_both_views():
    html = UI.page()
    line = lambda pre: html[html.index(pre): html.index("\n", html.index(pre))]
    cut = lambda pre: html[html.index(pre): html.index("\n}\n", html.index(pre)) + 3]
    src = "\n".join([line("const esc = s =>"), line("const ord = n =>"), cut("function shFill(d)"), cut("const RD_C = r =>")])
    d = pathlib.Path(tempfile.mkdtemp())
    # three teams, 10 games each: their opponents' rebounds against them, [g, reb, oreb, contested, dist x4, shot x4, miss3]
    (d / "t.js").write_text(src + """
const T = {BOS: [10, 380, 90, 160, 100, 150, 60, 70, 0, 0, 0, 0, 120], NYK: [10, 360, 80, 108, 120, 150, 60, 30, 0, 0, 0, 0, 100],
           ATL: [10, 380, 70, 190, 80, 150, 100, 50, 0, 0, 0, 0, 110], NOP: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]};
const me = [5, 50, 10, 20, 20, 15, 10, 5, 10, 10, 10, 20, 15], avg = {dist: [.4, .3, .2, .1], shot: [], contested: .5, miss3: .25};
console.log(JSON.stringify({def: rebRings(T.BOS, avg, T, "BOS"), me: rebRings(me, avg, null, "BOS"),
  fills: [shFill(0), shFill((6 / (220 / 30) - 1) * 50), shFill((7 / 5 - 1) * 50)]}));
""")
    out = json.loads(subprocess.run([NODE, str(d / "t.js")], capture_output=True, text=True, check=True).stdout)
    texts = lambda h, c: re.findall(f'class="{c}">([^<]+)<', h)
    fills = lambda h: re.findall(r'fill="([^"]+)" fill-rule', h)
    f0, f2, f3 = out["fills"]
    # the defense view: a game against them in each ring (10, 15, 6, 7), shaded against the league's a team-game
    # (10, 15, 7.33, 5; a team with no games left out), ranked 1st = the fewest (ties share the better rank)
    assert texts(out["def"], "rdv") == ["10.0", "15.0", "6.0", "7.0"] and fills(out["def"]) == [f0, f0, f2, f3]
    assert [x for x in texts(out["def"], "rds") if "ft" not in x] == ["2nd", "1st", "1st", "3rd"]
    assert "BOS's opponents grab them" in out["def"] and "10 games" in out["def"] and "Off missed threes" not in out["def"]
    assert "42%<small>league 41%</small>" in out["def"]                # contested: 160 of 380, the league 458 of 1120
    # his view: shares of his boards against the players with rebound lines, no ranks
    assert texts(out["me"], "rdv") == ["40%", "30%", "20%", "10%"] and fills(out["me"]) == [f0] * 4
    assert texts(out["me"], "rds") == ["0–3 ft", "3–6 ft", "6–10 ft", "10+ ft"] and "50 boards" in out["me"]
    assert "40%<small>avg 50%</small>" in out["me"] and "30%<small>avg 25%</small>" in out["me"]


def test_page_controls_work_on_iphone():
    html = UI.page()
    # every tap (and every 30 s, and a return to the app) checks the data file's Last-Modified with a bodiless HEAD, at
    # most every 8 s, and downloads it in the background only when the server wrote a new one; the same file again
    # (generated_at unchanged) is not redrawn
    assert 'document.addEventListener("click", freshen, true);' in html and "setInterval(freshen, 30000);" in html
    assert 'fetch("nba_props.json?t=" + Date.now(), {method: "HEAD", cache: "no-store"})' in html
    assert "return m && m !== LAST_MOD ? load() : null;" in html and 'LAST_MOD = r.headers.get("Last-Modified") || LAST_MOD;' in html
    assert "Date.now() - CHECK_AT < 8000" in html and "if (D) { CHECK_AT = 0; freshen(); }" in html
    assert "if (D && FRESH && !AUTO_DAY && j.generated_at === D.generated_at) { LOADED_AT = Date.now(); return true; }" in html
    # iOS Safari can't drag the thumb of a range input stacked under another, so the dual sliders are pointer-event widgets
    assert 'type="range"' not in html and "dualRange(" in html and "touch-action:pan-y" in html
    # a double tap doesn't zoom the page (taps on the stat chips, pills and bars come quickly); a pinch still does
    assert "*{box-sizing:border-box;-webkit-tap-highlight-color:transparent;touch-action:manipulation}" in html
    assert "user-scalable" not in html and "maximum-scale" not in html
    # the Pickz P (docs/icon.svg; icon-small.svg for the 64 px tab icon), versioned so a phone fetches the new one
    assert '<link rel="icon" href="icon-64.png?v=2">' in html and '<link rel="apple-touch-icon" href="icon-180.png?v=2">' in html
    # the headers (list, player and Matchup pages, all through --st) start 10 px below each iPhone's status bar /
    # Dynamic Island: its own safe-area inset, plus a gap
    assert "--st:calc(env(safe-area-inset-top) + 10px);" in html and html.count("env(safe-area-inset-top)") == 1
    # chart bars show their game on tap (a <title> only appears on hover); the book prices switch Over / Under
    assert "data-ps=" in html
    # a tap on a bar opens that game's box score (docs/box/{gid}.json, nba_boxscore), his row and the prop's stats marked
    assert 'if (gb) boxSheet(gb.dataset.gid, gb.dataset.tm, p);' in html and 'data-gid="${esc(l.gid)}"' in html
    assert "fetch(`box/${encodeURIComponent(gid)}.json`)" in html and "barTip(" not in html and ".tip{" not in html
    # the gauge opens the Matchup page (a page of its own in the history), with the opponent's recent games vs a position
    # group from docs/vs/{TEAM}.json (nba_vs): 5 rows, More / Less to 10, a row opens that game's box score
    assert '$("#mub", pg).onclick = () => { if (p.opp) openMatchup(p); };' in html and "function matchupSheet(" not in html
    # any player's page, prop or not: "v|<pid>|<market>" from docs/player/{pid}.json (nba_players), every stat's tab, a line
    # he sets (his average to the half below), no books; search finds any player; box score and Injuries rows open one
    assert "fetch(`player/${pid}.json`)" in html and 'fetch("player/index.json")' in html and "function propFor(id)" in html
    assert "line: p.v ? vLine(p) :" in html and "const mkts = p.v ? TAB_ORDER :" in html and 'if (p.v) { $("#pproj").innerHTML = ""; $("#pbk").innerHTML = ""; }' in html
    assert 'String(gid).startsWith("none:")' in html and "if (ST.view === \"props\" && q.length >= 2) searchPlayers(q);" in html
    assert '<tr data-vp="${r[0]}"' in html and 'data-vp="${e.pid}"' in html and "openPlayer(+v.dataset.vp)" in html
    assert "fetch(`vs/${encodeURIComponent(p.opp || \"\")}.json`)" in html and 'if (MUP) h.set("mu", "1");' in html
    assert 'if (MUP && !h.get("mu")) closeMatchup(swiped);' in html and "rows = all.slice(0, MUP.more ? 10 : 5)" in html
    assert 'boxSheet(t.dataset.g, t.dataset.t, {market: mk, pid: +t.dataset.pid})' in html and '<div id="mp" class="pg"' in html
    # the box score rises once, full height, with the box in it: fetched on touch-down and kept, the bars on screen
    # fetched while idle; if it is not here in 140 ms a same-shape skeleton rises and the box fades in over it
    assert "const BOXC = new Map();" in html and "cw.onpointerdown" in html and "boxWarm(win);" in html
    assert '.sheet[data-kind="box"]{height:86vh}' in html and "setTimeout(r, 140, null)" in html and 'class="bxsk"' in html
    assert "Loading…</div>', () => {});\n  const s = $(\"#sheet\"), n = SHEET_N;\n  s.dataset.kind = \"box\"" not in html
    # the Matchup page's shot chart (docs/shots/{season}.json, nba_shots): six zones shaded against the league, the
    # player or the opponent's defense, this season once the opponent has 10 games, and where it gets scored on
    assert '<div class="shc" id="shc"></div>' in html and "fetch(`shots/${encodeURIComponent(season)}.json`)" in html
    assert "MUP.shSeason = t && t.gp >= 10 ? D.season : prevSeason(D.season);" in html and "Where ${esc(p.opp)} gets scored on" in html
    assert "opp[k][0] * SH_PTS[k] / t.gp - j.league[k][0] * SH_PTS[k] / games" in html and "SH_PATH.length" not in html
    # the shot dots (docs/shots/p/{pid}.json): every shot on a to-scale court (the corner line 22 ft out, so a dot lands
    # in its zone), made green over missed red rings, Shots by default for the player, Zones as before; defense: zones
    assert "const SH_R3 = 237.5, SH_CX = 220," in html and "fetch(`shots/p/${pid}.json`)" in html
    assert 'shView: "player", shSeason: null, shMode: "shots"' in html and 'const dotsOn = MUP.shView !== "def" && MUP.shMode !== "zones";' in html
    # Movers (a line moved since open, or the books disagree: the move first), Lineups beside Injuries (NEW starters, the usual
    # five not starting), who guards him on the Matchup page (docs/matchups/{pid}.json, nba_defmatch)
    assert 'if (ST.market === "movers") return list.map(p => [p, mover(p)])' in html and "k: Math.abs(mv) * 100 + gap" in html
    assert '(ST.iv === "lu" ? lineupsView() : ST.iv === "ro" ?' in html and "function luTeam(t, e)" in html and 'isNew(pid) ? " · NEW" : ""' in html
    # role changes (docs/player/roles.json), the Live tab (props under way from their closing boards: only there), game script
    assert 'fetch("player/roles.json")' in html and "function rolesView(" in html and 'data-iv="ro"' in html
    assert 'const ALL_TABS = ["live", "trends", "movers"];' in html and "list = list.filter(p => !p.closed);" in html
    # the flags (D.flags: the under plays that ping) are the bottom bar's Flags view, in place of Markets (a saved
    # Markets view opens Props), SHADOW · NOT A BET, each graded at its own line once final; a chip on the prop's row
    # and a line on its page; a tap opens the prop or the player. The props section has no Flags tab
    assert 'const VIEWS = [["props", "Props"], ["flags", "Flags"], ["injuries", "Injuries"]];' in html and "mrow" not in html
    assert 'if (["props", "flags", "injuries"].indexOf(ST.view) < 0) ST.view = "props";' in html and '"markets"' not in html
    assert '  if (ST.view === "flags") { lst.innerHTML = flagsView(); return; }' in html and 'flags: "Flags"' not in html
    assert 'if (ml) ml.style.display = ST.view === "props" ? "" : "none";' in html and 'if (ST.view === "props" && q.length >= 2)' in html
    assert "${flagChips(p)}</div>" in html and "const flagChips = p => flagsOf(p.id).length ?" in html
    assert "f.date === ST.date && (ST.gid === \"all\" || f.gid === ST.gid)" in html
    assert 'g.state === "final" ? flagGrade(f.side, f.line, p.live.value) : null' in html
    assert '${p ? `data-id="${esc(id)}"` : `data-vp="${f.pid}"`}' in html and html.count("SHADOW · NOT A BET") == 3
    assert "function liveRow(p)" in html and 'st = liveStatus(x.v, x.line, over, live)' in html
    assert 'if (f.blow === "b" && !(Math.abs(l.margin) >= 15)) return false;' in html and 'tchip("blow", "b", "Blowouts")' in html
    assert "function gameScript(p, g, logs, line, side)" in html and '<span class="gsp">' in html
    # schedule spots: a card on the player page, the back-to-back team in orange on its game card
    assert "function schedCard(p, g, logs, line, side)" in html and '$("#psc").innerHTML = schedCard(' in html and "function cardNote(g)" in html
    # referees: docs/refs.json (nba_refs) on the Matchup page and one line in the game script; officials under 10 games left out of the crew's mean
    assert 'fetch("refs.json?t="' in html and '<div class="shc wg" id="rfc"></div>' in html and "refCard();" in html and "refsRow(p, g);" in html
    assert "d: r && r[1] >= 10 ?" in html
    # the combo checker: kept on the phone, opened from the floating button, the math in the shared core
    assert 'localStorage.getItem("pickz_combo")' in html and "comboStats(L, CMB_W, D.season)" in html and 'id="cmb"' in html and "comboPill();" in html
    assert "fetch(`matchups/${pid}.json`)" in html and '<div class="shc wg" id="wgd"></div>' in html and "guardCard();" in html
    # the floating header fades what scrolls under it (no text under its title)
    assert '.ph::before{content:"";position:absolute;' in html
    # every sheet in the player page's look: near-black with a thin edge, capsule toggles, outline chips and buttons,
    # the main action white, the chart filters' capsule slider; no iOS grey sheet, blue button or blue slider
    import re
    assert "background:#0c0c0c" in html and ".btn.pri{border-color:#fff;background:#fff;color:#000}" in html
    assert re.search(r"\.seg\{[^}]*border:1px solid #2a2a2a;border-radius:21\.2px", html) and ".seg button[aria-pressed=\"true\"]{background:#313131}" in html
    assert 'class="dual"' not in html and "background:var(--blue)" not in html and "background:#1c1c1e" not in html
    # the reference layout: Trends tab, game cards, a floating Props / Markets / Injuries bar, a books table
    assert all(k in html for k in ('trends: "Trends"', 'class="gc"', 'data-view="', '["injuries", "Injuries"]', 'id="pbk"'))
    # the Watchlist is a filter now (an old #view=watch link lands on it); a teammate named in an injury read opens his prop
    assert '["watch", "Watchlist"]' not in html and 'Object.assign(ST, {view: "props", watch: "1"})' in html and "data-wl=" in html
    assert ".ijb[data-id]" in html and "function injView(" in html and 'ST.view === "injuries"' in html
    # the prop page's With / Without: any teammate, several at once, from the chip's sheet or the full filter sheet
    assert "function mateSheet(" in html and "data-mk2=" in html and "with: ms.filter(m => x.with[m.key]), without: ms.filter(m => x.without[m.key])" in html
    assert html.count("bindMates(s, dr, upd);") == 2
    # chart filters on one scrolling row, nothing behind a More toggle; the row keeps its place when a chip re-renders it
    assert ".fcs{display:flex;flex-wrap:nowrap" in html and 'id="more"' not in html and '$$("#pcf .fcs").forEach((x, i) => x.scrollLeft = fl[i] || 0);' in html
    # the With / Without button heads a row of its own just below the stat chips, before any open range slider
    assert """<div class="fcs">${chips.join("")}</div>${mchips.length ? `<div class="fcs fcw">${mchips.join("")}</div>` : ""}${panels}""" in html
    assert """if (ms.length) mchips.push(chip('id="mts\"""" in html and html.count("""chip('id="mts\"""") == 1
    assert html.index("if (ms.length) mchips.push(") < html.index("without.filter(w => w.fresh).forEach(w => mchips.push(")
    # another stat of the same player keeps his filters and window (only the line resets); a range his new stat has no
    # use for (potential assists on points) stays set but neither filters nor draws until he is back on assists
    assert "const same = was && who(CUR) === who(id);" in html and "fresh: null}, same ? {} : {" in html
    assert "if (forMarket(k, p.market)) ranges[k] = x.ranges[k];" in html and "ranges: ranges, oppSets: oppSets" in html
    assert "const ovOn = k => forMarket(k, p.market) && !!(DT.open[k] || DT.ranges[k]);" in html
    # the Injuries view is one list, most relevant first (minutes x the chance he sits); no Injuries tab among the Props tabs
    assert "injList().sort" not in html and "return out.sort((a, b) => injImpact(b) - injImpact(a));" in html
    # a Starter chip after the adjustable filters; a prop opens on this season's window; hit-rate boxes show a percentage
    assert html.index('.forEach(rchip);') < html.index('tchip("starter", true, "Starter")') < html.index("if (c.dvp_rank) chips.push(")
    assert 'win: windowed(logsOf(p), "season", D.season).length ? "season" : "l10"' in html
    assert 'if (x.n < 5) return {t: pct(x.rate), c: "sm"};' in html and 'h + "/" + x.n' not in html
    assert "ALL_TABS = [" in html and 'injury: "Injuries"' not in html and '"injury"' not in html
    # motion runs as Web Animations with a timer fallback, and nothing is fetched from a font CDN
    assert ".animate([" in html and "setTimeout(done" in html and "fonts.googleapis" not in html
    # every range chip but Margin draws its stat on the chart as white outline boxes (Margin can be negative: filter only)
    assert ('const OVL = {min: "min", fga: "FGA", fg3a: "3PTA", fta: "FTA", usg: "usage %", pot_ast: "potential assists", '
            'reb_ch: "rebound chances"}') in html and "l[ov]" in html
    # the adjustable filters come first; potential assists / rebound chances only on the props they bear on
    assert '["min", "fga", "fg3a", "fta", "usg", "pot_ast", "reb_ch"].forEach(rchip)' in html
    assert html.index('.forEach(rchip);') < html.index("if (c.dvp_rank) chips.push(") < html.index('rchip("margin");')
    assert 'pot_ast: ["assists", "pra", "pts_ast", "reb_ast"], reb_ch: ["rebounds", "pra", "pts_reb", "reb_ast"]' in html
    # no explanatory prose: notes are status only, empty states are titles only
    import re
    notes = re.findall(r'class="note"[^>]*>([^<$]*)', html)
    assert all(n.strip() in ("Loading…", "") or n.startswith("Couldn") for n in notes), notes
    assert not re.search(r'<div class="empty"><b>[^<]+</b>[A-Za-z]', html)
    # research+: fair price / VALUE, honest hit-rate boxes, Trends + Injuries tabs, line history, books that disagree
    assert all(k in html for k in ("fairAt(", "<i>VALUE</i>", "hbox(", "histChart("))
    # 6-7: the alt-line ladder (one-sided rungs colored against their own implied chance) and the scorecard sheet
    assert all(k in html for k in ("function ladder(", "chanceSide(", "data-ll=", "nba_research_score.json", "scoreSheet"))
    # 6: the alt-line ladder (tap a rung to use it); 7: the scorecard sheet reads the nightly replay's JSON
    assert "function ladder(" in html and "data-ll=" in html and "nba_research_score.json" in html and "function scoreSheet(" in html


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_page_never_hides_the_projection_record():
    html = UI.page()
    # the user's rule: never conceal that the model lost to FanDuel's close or that the blend added nothing; not-a-bet stays
    assert "MODEL ESTIMATE · NOT A BET" in html and 'vs FanDuel close</span><b class="dn">Lost</b>' in html and 'Blend with the price</span><b>Added nothing</b>' in html
    assert "TUNING · IN-SAMPLE" in html and "(p.label ?" in html and "Pre-registered verdicts" in html
    assert html.count('NOT A BET</span></h2>') == 4 and "NONE · RESEARCH ONLY" in html
    # the verdict rows split the pre-registered sentences into claim / YES-NO / reason
    rx = r'/^(.*):\s*(YES|NO)\b\s*(.*?)\.?$/'
    assert rx in html
    vs = ["M1 projects stats better than B2 (CRPS, A and B): YES.",
          "M1 is calibrated (FanDuel-line reliability within 3 pts and PIT deciles 10-12% on A): NO (reliability fails, PIT fails).",
          "M1 beats FanDuel's close (model - close log loss, A and C): NO."]
    js = f"const r = {rx}; console.log(JSON.stringify(process.argv.slice(1).map(v => (m => m && [m[1], m[2], m[3]])(r.exec(v)))))"
    out = json.loads(subprocess.run([NODE, "-e", js, *vs], capture_output=True, text=True, check=True).stdout)
    assert out == [["M1 projects stats better than B2 (CRPS, A and B)", "YES", ""],
                   ["M1 is calibrated (FanDuel-line reliability within 3 pts and PIT deciles 10-12% on A)", "NO", "(reliability fails, PIT fails)"],
                   ["M1 beats FanDuel's close (model - close log loss, A and C)", "NO", ""]], out


def test_board_links_the_page():
    import nba_board as B
    assert 'href="nba_props.html"' in B.html({"record": None, "slates": [], "retracted": [], "offcard": []})


def test_write_is_atomic(payload):
    d = pathlib.Path(tempfile.mkdtemp())
    RS.write(d, payload)
    assert json.loads((d / "nba_props.json").read_text())["props"] and (d / "nba_props.html").read_text().startswith("<!doctype")
    assert not list(d.glob(".*.tmp"))


# ── prices, the change log, blended ranks, fresh absences (research+ 2026-10-26) ──────────────────────────────
def test_replay_carries_the_board_forward():
    # quotes is a CHANGE log: t2 writes only the over that moved, t3 pulls the 20.5 rung (odds NULL)
    rows = [("t1", "fd", "G", 7, "points", 20.5, "over", 1.9), ("t1", "fd", "G", 7, "points", 20.5, "under", 1.9),
            ("t1", "fd", "G", 7, "points", 21.5, "over", 2.2), ("t1", "fd", "G", 7, "points", 21.5, "under", 1.65),
            ("t2", "fd", "G", 7, "points", 20.5, "over", 2.05),
            ("t3", "fd", "G", 7, "points", 20.5, "over", None), ("t3", "fd", "G", 7, "points", 20.5, "under", None)]
    mains = [(t, RS.main_of(st[("G", 7, "points", "fd")])) for t, st in RS.replay(iter(rows))]
    assert mains == [("t1", (20.5, 1.9, 1.9)), ("t2", (20.5, 2.05, 1.9)), ("t3", (21.5, 2.2, 1.65))]
    d = pathlib.Path(tempfile.mkdtemp())
    q = sqlite3.connect(d / "l.sqlite")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT, stat TEXT, "
              "line REAL, side TEXT, odds REAL)")
    q.executemany("INSERT INTO quotes VALUES (?,?,?,'',?,'',?,?,?,?)", [(t.replace("t", "2026-10-26T0") + ":00:00", *r)
                                                                        for t, *r in rows])
    h = RS.line_history(q, ["G"])[("G", 7, "points")]["fd"]
    assert [x[1:] for x in h] == [[20.5, 1.9, 1.9], [20.5, 2.05, 1.9], [21.5, 2.2, 1.65]]


def test_fair_value_and_z():
    books = {"fd": {"rungs": [[20.5, 1.9, 1.9], [24.5, 3.0, None]]}, "dk": {"rungs": [[20.5, 2.0, 1.8]]}}
    nv_dk = (1 / 2.0) / (1 / 2.0 + 1 / 1.8)
    f, n = RS.fair_at(books, 20.5)
    assert n == 2 and f == pytest.approx((0.5 + nv_dk) / 2)
    v = RS.value_at(books, 20.5, "over")
    assert v["book"] == "dk" and v["ev"] == pytest.approx(2.0 * f - 1)              # the best over, against fair
    assert RS.value_at(books, 20.5, "under")["ev"] == pytest.approx(1.9 * (1 - f) - 1)
    assert RS.fair_at(books, 24.5) == (None, 0) and RS.value_at(books, 24.5, "over") is None   # one-sided: no fair
    assert RS.zscore(7, 10, .5) == pytest.approx(2 / math.sqrt(2.5)) and RS.zscore(3, 3, None) is None


class _FakeSeason:
    """The slice of nba_matchup.Season that rank_tables_blend reads. rate = what a team allowed per possession."""
    def __init__(self, rates, n, lg=1.0):
        self.rates, self.nn, self.lg = rates, n, lg
        self.by_team = {t: [] for t in rates}
        self.games, self.poss = {}, {}

    def _team_before(self, t, d):
        n = self.nn.get(t, 0)
        return n, 100.0 * n, {("G", "pts"): self.rates[t] * 100.0 * n}

    def _league_before(self, d):
        return 1, 100.0, {("G", "pts"): self.lg}

    def group_factors(self, t, d, g, lg=None):
        return {"pts": self.rates[t] / self.lg}


def test_rank_tables_blend_moves_from_last_season_to_this_one():
    m = sqlite3.connect(":memory:")
    m.execute("CREATE TABLE games (gid TEXT, home_pts REAL, away_pts REAL)")
    prev = _FakeSeason({"A": 0.9, "B": 1.0, "C": 1.1}, {})          # last season: A the toughest, C the softest
    cur_rates = {"A": 1.2, "B": 1.0, "C": 0.8}                      # this season the other way round
    early = RS.rank_tables_blend(_FakeSeason(cur_rates, {"A": 2, "B": 2, "C": 2}), prev, m, "2026-10-26")
    late = RS.rank_tables_blend(_FakeSeason(cur_rates, {"A": 60, "B": 60, "C": 60}), prev, m, "2027-03-01")
    assert early["dvp"]["G"]["points"] == {"A": 1, "B": 2, "C": 3} and early["n"]["A"] == 2       # 2 games: last season
    assert late["dvp"]["G"]["points"] == {"A": 3, "B": 2, "C": 1}                                  # 60 games: this one
    assert early["teams"] == 3


def test_absences_mark_fresh_news():
    official = {(GD, 3): {"status": "Out", "team": "PHX"}, (GD, 4): {"status": "Out", "team": "PHX"}}
    rows = lambda gids: [("2026-09-%02d" % (i + 1), g, "PHX", "UTA", 1, 1, 30.0) + (None,) * 9 for i, g in enumerate(gids)]
    by_team = {3: {"PHX": rows([f"g{i}" for i in range(12)])},                   # played the team's last game
               4: {"PHX": rows([f"x{i}" for i in range(12)])}}                   # long gone: none of the last 2
    out = RS.absences(official, by_team, [GD], {"PHX": ["g10", "g11"]})[(GD, "PHX")]
    assert {a["pid"]: a["fresh"] for a in out} == {3: True, 4: False} and out[0]["mpg"] == 30.0


def _injury_fixture():
    m = MU.connect(pathlib.Path(tempfile.mkdtemp()) / "m.sqlite")
    PG = "INSERT INTO player_games (gid, team, pid, pos, starter, min) VALUES (?,?,?,?,?,?)"
    games = [(f"a{i}", "2025-26", f"2026-03-{i + 1:02d}") for i in range(10)] + [(f"b{i}", "2026-27", f"2026-10-2{i + 1}") for i in range(2)]
    for gid, s, d in games:
        m.execute("INSERT INTO games (gid, season, date, home, away, home_pts, away_pts) VALUES (?,?,?,?,?,100,90)", (gid, s, d, "PHX", "UTA"))
        i, last = int(gid[1:]), s == "2025-26"
        out = not last or i >= 6                               # X (10) hurt after game a5, still out this season
        if not out:
            m.execute(PG, (gid, "PHX", 10, "C", 1, 30))
        m.execute(PG, (gid, "PHX", 11, "G", 1, 32))                                   # A: starts either way
        m.execute(PG, (gid, "PHX", 12, "C" if out else "", int(out), 28 if out else 12))   # B: starts in X's place
        m.execute(PG, (gid, "PHX", 13, "", 0, 20 if out else 15))                     # C: +5 a game without X
        if last and i in (2, 3):
            m.execute(PG, (gid, "PHX", 15, "", 0, 12))         # Z: a bench player in 2 of the 8 games since his first
        if last and i >= 6:
            m.execute(PG, (gid, "PHX", 14, "", 0, 5))          # T: a two-way, 5 minutes
        if not last:
            m.execute(PG, (gid, "PHX", 16, "G", 1, 24))        # N: new this season, starts; never played beside X
        m.execute(PG, (gid, "UTA", 20, "G", 1, 34))            # Y: a starter who never missed a game
        m.execute(PG, (gid, "UTA", 21, "", 0, 18))             # W: the bench guard with the most minutes
        m.execute(PG, (gid, "UTA", 22, "", 0, 10))
        m.execute(PG, (gid, "UTA", 23, "", 0, 25))             # U: more minutes, but a forward
        if last:
            m.execute(PG, (gid, "SAC", 30, "F", 1, 31))        # K: all of last season for SAC, on PHX now
    m.commit()
    roster = {"10": ["PHX", "X Ten", "C"], "11": ["PHX", "A Eleven", "G"], "12": ["PHX", "B Twelve", "C"],
              "13": ["PHX", "C Thirteen", "F"], "14": ["PHX", "T Fourteen", "G"], "15": ["PHX", "Z Fifteen", "G"],
              "20": ["UTA", "Y Twenty", "G"], "21": ["UTA", "W TwentyOne", "G"], "22": ["UTA", "V TwentyTwo", "G"],
              "23": ["UTA", "U TwentyThree", "F"], "30": ["PHX", "K Thirty", "F"], "16": ["PHX", "N Sixteen", "G"]}
    d = "2026-10-26"
    official = {(d, 10): {"status": "Out", "team": "PHX", "reason": "Injury/Illness - Knee"},
                (d, 15): {"status": "Questionable", "team": "PHX", "reason": ""},
                (d, 11): {"status": "Questionable", "team": "PHX", "reason": ""},
                (d, 14): {"status": "Out", "team": "PHX", "reason": "G League - Two-Way"},
                (d, 30): {"status": "Out", "team": "PHX", "reason": ""},
                (d, 20): {"status": "Doubtful", "team": "UTA", "reason": ""},
                (d, 99): {"status": "Out", "team": "PHX", "reason": "", "player": "Not Indexed"}}
    args = (official, {(d, "PHX"): True, (d, "UTA"): True}, {d: {"published": "2026-10-26T21:30:00+00:00"}},
            [{"date_et": d, "home": "PHX", "away": "UTA"}], roster, ("2025-26", "2026-27"))
    return m, args


def test_injury_report_reads_who_took_the_minutes():
    m, args = _injury_fixture()
    out = RS.injury_report(m, *args)
    phx, uta = out["2026-10-26|PHX"], out["2026-10-26|UTA"]
    assert phx["listed"] and phx["published"].startswith("2026-10-26T21:30")
    assert [e["pid"] for e in phx["players"]] == [30, 10, 14, 99, 11, 15]      # Out by minutes, then Questionable
    # NEW: played in one of the team's last 2 games (A did; X has sat since last season)
    assert {e["pid"]: e["fresh"] for e in phx["players"]} == {30: False, 10: False, 14: False, 99: False, 11: True, 15: False}
    x = next(e for e in phx["players"] if e["pid"] == 10)
    # 4 games after he got hurt last season + this season's 2 (still on the team): 6 missed beside 6 played
    assert x["starter"] and x["missed"] == 6 and x["mpg"] == 30.0 and x["season"] == "2025-26"
    assert x["starts"] == {"pid": 12, "name": "B Twelve", "k": 6, "n": 6, "how": "games"}
    assert [(g["pid"], g["gain"], g["n"]) for g in x["minutes"]] == [(12, 16.0, 6), (13, 5.0, 6)]   # not A (+0)
    k = next(e for e in phx["players"] if e["pid"] == 30)                      # last season was SAC's: no PHX games
    assert k["missed"] == 0 and k["starts"] is None and k["minutes"] == [] and k["mpg"] == 31.0
    t = next(e for e in phx["players"] if e["pid"] == 14)                      # under 10 a game: listed, no read
    assert t["mpg"] == 5.0 and t["minutes"] == [] and t["starts"] is None
    z = next(e for e in phx["players"] if e["pid"] == 15)                      # in 2 of 8: the games he played are odd
    assert z["missed"] > 2 and z["minutes"] == [] and z["status"] == "Questionable"
    assert next(e for e in phx["players"] if e["pid"] == 99)["name"] == "Not Indexed"
    y = uta["players"][0]                                                      # never missed: the bench guard
    assert y["missed"] == 0 and y["starts"] == {"pid": 21, "name": "W TwentyOne", "k": None, "n": None, "how": "position"}


def test_mutants_injury_report():
    m, args = _injury_fixture()
    player = lambda out, pid: next(e for e in out["2026-10-26|PHX"]["players"] if e["pid"] == pid)

    def mutant(old, new):
        src = inspect.getsource(RS.injury_report)
        assert src.count(old) == 1, old
        ns = {}
        exec(compile(src.replace(old, new), "mutant", "exec"), RS.__dict__, ns)
        return ns["injury_report"](m, *args)
    # 1. his window stops at his last game (a sitting player's later games not counted as missed)
    real = RS.depth_read
    RS.depth_read = lambda boxes, x, mates, stays: real(boxes, x, mates, {})
    try:
        assert player(RS.injury_report(m, *args), 10)["missed"] != 6
    finally:
        RS.depth_read = real
    # 2. a bench player out more often than in still gets a read: teammates "gain" in the games he sat
    assert player(mutant("elif not starter and played < missed:", "elif False:"), 15)["minutes"]
    # 3. the starts read without a with-him baseline: N, who never played beside X, takes his spot
    assert player(mutant("and nw >= MIN_WITHOUT and so / no >= .5 and sw / nw < .5",
                         "and so / no >= .5 and (not nw or sw / nw < .5)"), 10)["starts"]["pid"] == 16
    # 4. a player with no game for the team gets the by-position guess anyway
    assert player(mutant("if starter and played:", "if starter:"), 30)["starts"] is not None
    # 5. NEW from every game he ever played, not the team's last 2: X, out since last season, reads as news
    assert player(mutant("if b[1] < d][-FRESH_GAMES:]", "if b[1] < d]"), 10)["fresh"] is True


def test_mutants_research_plus():
    """Each guard above must fail on the bug it exists for."""
    import importlib
    src = pathlib.Path(RS.__file__).read_text()
    cases = (
        ("snapshot reading of the change log (the 2026-10-26 audit bug)",
         "        k = (gid, pid, stat, book)\n", "        k = (gid, pid, stat, book)\n        state[k] = {} if k not in dirty else state[k]\n",
         test_replay_carries_the_board_forward),
        ("no blend: this season's 2 games decide", "f[st_] = (n * r + k * pf * lg_r) / (n + k) / lg_r",
         "f[st_] = r / lg_r", test_rank_tables_blend_moves_from_last_season_to_this_one),
        ("every absence is fresh", '"fresh": any(g in played for g in (team_last or {}).get(team, []))',
         '"fresh": True', test_absences_mark_fresh_news))
    for tag, a, b, test in cases:
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_research.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        saved = sys.modules.pop("nba_research")
        try:
            mut = importlib.import_module("nba_research")
            globals()["RS"] = mut
            try:
                test()
            except AssertionError:
                continue                                  # caught
            raise AssertionError(f"MUTANT survived: {tag}")
        finally:
            globals()["RS"] = saved
            sys.modules["nba_research"] = saved
            sys.path.remove(str(d))


def test_lineups_flags_new_starters_and_missing_regulars():
    import zlib
    lc = sqlite3.connect(":memory:")
    lc.execute("CREATE TABLE snaps (fetched_at TEXT, date_et TEXT, sha TEXT, body BLOB)")
    P = lambda pid, nm, pos, st="Confirmed", ro="Active", ts="2026-10-26T22:32:00": {
        "personId": pid, "playerName": nm, "position": pos, "lineupStatus": st, "rosterStatus": ro, "timestamp": ts}
    early = {"games": [{"gameId": "G1", "homeTeam": {"teamAbbreviation": "PHX", "players": [P(1, "A One", "PG", "Expected")]}}]}
    late = {"games": [{"gameId": "G1", "homeTeam": {"teamAbbreviation": "PHX", "players": [
        P(1, "A One", "PG"), P(2, "B Two", "SG"), P(3, "C Three", "SF"), P(4, "D Four", "PF", ts="2026-10-26T22:40:00"),
        P(9, "New Nine", "C"), P(5, "E Five", ""), P(6, "F Six", "", ro="Inactive")]},
        "awayTeam": {"teamAbbreviation": "SAC", "players": [P(20, "Exp Twenty", "PG", "Expected")]}}]}
    lc.execute("INSERT INTO snaps VALUES ('2026-10-26T20:00:00+00:00', ?, 'a', ?)", (GD, zlib.compress(json.dumps(early).encode())))
    lc.execute("INSERT INTO snaps VALUES ('2026-10-26T23:00:00+00:00', ?, 'b', ?)", (GD, zlib.compress(json.dumps(late).encode())))
    # PHX's last 10 games before tonight: 1-5 start every one (5 is its regular center); an older game does not count
    boxes = {"PHX": [(f"g{i}", f"2026-10-{i + 1:02d}", "2026-27", {**{k: (1, 30) for k in (1, 2, 3, 4, 5)}, 9: (0, 12)})
                     for i in range(11)] + [("g99", GD, "2026-27", {7: (1, 30)})]}           # tonight's own: not before it
    boxes["SAC"] = [(f"s{i}", f"2026-10-2{i}", "2026-27", {21: (1, 30)}) for i in (1, 3)]      # 2 games this season
    boxes["SAC"] += [(f"o{i}", f"2026-03-{i + 1:02d}", "2025-26", {22: (1, 30)}) for i in range(10)]   # last season's
    out = RS.lineups(lc, [GD, "2026-10-27"], boxes, {(GD, 5): {"status": "Questionable"}})
    assert out[f"{GD}|SAC"]["usual"] == [] and out[f"{GD}|SAC"]["missing"] == []      # under 3 this season: nothing marked
    e = out[f"{GD}|PHX"]
    assert e["status"] == "Confirmed" and e["at"] == "2026-10-26T22:40:00"                     # the latest snapshot
    assert [s[0] for s in e["starters"]] == [1, 2, 3, 4, 9] and e["starters"][4] == [9, "New Nine", "C"]
    assert sorted(e["usual"]) == [1, 2, 3, 4, 5] and e["missing"] == [[5, "E Five", "Questionable"]]
    assert e["inactive"] == [[6, "F Six"]] and out[f"{GD}|SAC"]["status"] == "Expected"
    assert not any(k.startswith("2026-10-27") for k in out)                                    # no snapshot yet


def test_closing_boards_keep_started_games_props():
    d = pathlib.Path(tempfile.mkdtemp())
    q = sqlite3.connect(d / "lines.sqlite")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT, stat TEXT, "
              "line REAL, side TEXT, odds REAL)")
    tip = "2026-10-26T23:00:00"
    rows = [("2026-10-26T20:00:00", "fd", 5, "Coby White", "points", 18.5, "over", 1.98), ("2026-10-26T20:00:00", "fd", 5, "Coby White", "points", 18.5, "under", 1.86),
            ("2026-10-26T20:00:00", "fd", 5, "Coby White", "points", 21.5, "over", 3.1),
            ("2026-10-26T23:20:00", "fd", 5, "Coby White", "points", 25.5, "over", 1.9),        # in-game: not the close
            ("2026-10-26T23:20:00", "fd", 5, "Coby White", "points", 25.5, "under", 1.9)]
    q.executemany("INSERT INTO quotes VALUES (?,?, 'G1', ?, ?,?,?,?,?,?)", [(t, b, tip, p, n, s, ln, sd, o) for t, b, p, n, s, ln, sd, o in rows])
    q.commit()
    cache = d / "close.json"
    out, names = RS.closing_boards(q, ["G1"], cache=cache)
    fd = out[("G1", 5, "points")]["fd"]
    assert fd["rungs"] == [[18.5, 1.98, 1.86], [21.5, 3.1, None]] and fd["main"] == 18.5 and names[("G1", 5)] == "Coby White"
    q.execute("DELETE FROM quotes"); q.commit()                     # a started game's board never changes: the cache serves
    out2, names2 = RS.closing_boards(q, ["G1"], cache=cache)
    assert out2 == out and names2 == names


def test_schedule_spots():
    g = lambda gid, d, home, away, st="": {"gid": gid, "date_et": d, "home": home, "away": away, "status_text": st}
    sched = [g("a", "2026-10-20", "BOS", "NYK"), g("b", "2026-10-22", "MIA", "BOS"), g("c", "2026-10-23", "ORL", "BOS"),
             g("p", "2026-10-24", "ATL", "BOS", "PPD"),                                   # postponed: not a game
             g("d", "2026-10-25", "CHA", "BOS"), g("e", "2026-10-26", "BOS", "NYK"), g("f", "2026-10-29", "NYK", "MIA")]
    sp = RS.schedule_spots(sched, ["a", "c", "d", "e", "f"])
    assert sp["a"]["BOS"] == {"rest": None, "b2b": False, "g3in4": False, "g4in6": False, "trip": None}
    assert sp["c"]["BOS"] == {"rest": 0, "b2b": True, "g3in4": True, "g4in6": False, "trip": [2, 3]}   # 20, 22, 23
    assert sp["d"]["BOS"]["trip"] == [3, 3] and sp["d"]["BOS"]["g3in4"] and sp["d"]["BOS"]["rest"] == 1
    assert sp["e"]["BOS"] == {"rest": 0, "b2b": True, "g3in4": True, "g4in6": True, "trip": None}   # 22, 23, 25, 26
    assert sp["e"]["NYK"]["rest"] == 5 and sp["e"]["NYK"]["trip"] == [2, 2] and sp["f"]["MIA"]["trip"] == [1, 1]   # NYK away the 20th too; MIA home the 22nd
    assert "b" not in sp and "p" not in sp


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_combo_stats():
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "core.js").write_text(UI.JS_CORE)
    # A: points over 20.5 in g1-g5; B (a teammate who sat g3): rebounds under 6.5; C: never played with them
    a = [{"gid": f"g{k}", "date": f"2026-10-2{k}", "v": v} for k, v in enumerate([25, 18, 30, 22, 21], 1)]
    b = [{"gid": f"g{k}", "date": f"2026-10-2{k}", "v": v} for k, v in [(1, 4), (2, 5), (4, 9), (5, 3)]]
    b.append({"gid": "g0", "date": "2025-04-01", "v": 2})                     # last season, A had no game: not shared
    c = [{"gid": "x1", "date": "2026-10-21", "v": 10}]
    (d / "t.js").write_text("""
const C = require('./core.js');
const a = %s, b = %s, c = %s;
const legs = [{logs: a, line: 20.5, side: 'over'}, {logs: b, line: 6.5, side: 'under'}];
console.log(JSON.stringify([C.comboStats(legs, 'all', '2026-27'), C.comboStats(legs, 'l10', '2026-27').n,
  C.comboStats(legs.concat([{logs: c, line: 5, side: 'over'}]), 'all', '2026-27').n,
  C.comboStats([{logs: a, line: 20.5, side: 'over'}, {logs: a.map(x => Object.assign({}, x, {v: x.v / 5})), line: 4.5, side: 'over'}], 'all', '2026-27')]));
""" % (json.dumps(a), json.dumps(b), json.dumps(c)))
    full, l10, none, same = json.loads(subprocess.run([NODE, str(d / "t.js")], capture_output=True, text=True, check=True, cwd=d).stdout)
    assert [x["gid"] for x in full["games"]] == ["g1", "g2", "g4", "g5"]          # the games both played, oldest first
    assert [x["all"] for x in full["games"]] == [True, False, False, True] and (full["k"], full["n"]) == (2, 4)
    assert full["each"] == [0.75, 0.75] and full["indep"] == 0.5625 and full["rate"] == 0.5
    assert l10 == 4 and none == 0
    assert (same["k"], same["n"]) == (2, 5)                    # one player's two props share every game; only 25 → 5, 30 → 6 hit both


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_price_sorts_follow_the_book_filter():
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "core.js").write_text(UI.JS_CORE)
    # A: FanDuel's best by far, DraftKings poor; B: the reverse. Filtered to DraftKings, B's price and value lead
    q = lambda o, u: {"main": 20.5, "rungs": [[20.5, o, u]]}
    props = [{"id": "A", "main": 20.5, "books": {"fd": q(2.4, 1.6), "dk": q(1.7, 2.1)}},
             {"id": "B", "main": 20.5, "books": {"fd": q(1.8, 2.0), "dk": q(2.0, 1.8)}}]
    (d / "t.js").write_text("""
const C = require('./core.js'), ps = %s, ids = l => l.map(p => p.id);
console.log(JSON.stringify([ids(C.sortProps(ps, 'odds', 'desc', () => [], 'over', '2026-27')), ids(C.sortProps(ps, 'odds', 'desc', () => [], 'over', '2026-27', 'dk')),
  ids(C.sortProps(ps, 'value', 'desc', () => [], 'over', '2026-27', 'dk')), C.valueAt(ps[0], 20.5, 'over', 'dk').book]));
""" % json.dumps(props))
    allb, dk, dkv, book = json.loads(subprocess.run([NODE, str(d / "t.js")], capture_output=True, text=True, check=True, cwd=d).stdout)
    assert allb == ["A", "B"] and dk == ["B", "A"] and dkv == ["B", "A"] and book == "dk"


def test_page_navigation_guards():
    html = UI.page()
    # game cards' tap handler stays on the cards (the chart bars carry data-gid too); a stale game filter goes with its day
    assert '$$("[data-gid]", gcs)' in html and 'if (ST.gid !== "all" && !D.games.some(g => g.gid === ST.gid && g.date === ST.date)) ST.gid = "all";' in html
    # a books-table line only when it is a number; the line sheet's −/+ are a draft until Done
    assert '$$("button.bl", pg)' in html and "if (isFinite(l) && DT.line !== l)" in html and "const done = () => { closeSheet(); if (DT.line !== v)" in html
    # the Matchup page's search goes back as deep as the app went; a late player load or box score opens only where it was asked
    assert "history.go(-Math.max(1, navDepth()))" in html and "d: navDepth() + 1" in html
    assert "if (tok === OPEN_N && CUR === at) openProp(id, push)" in html and "if (SHEET_N !== n0 || CUR !== at || MUP !== mu) return;" in html
    # a refresh: side files refetch, an open page redraws only if its data moved, after a finger lifts, keeping the game log open
    assert "REFS = null; ROLES = null;" in html and "if (CUR && pageSig(CUR) !== pg0) redrawPage();" in html and "if (PDOWN) { REDRAW = true; return; }" in html


def test_page_boots_from_its_last_copy_and_animates_swaps():
    html = UI.page()
    # no pull to refresh (the user found it bad); the 2-minute refresh and the back-from-another-app refresh stay
    assert "pullRefresh" not in html and ".ptr" not in html and "setInterval(load, 120000)" not in html and '"visibilitychange"' in html
    # a launch draws the phone's last copy (Cache Storage) while the fresh one downloads; no "Feed delayed" off a stale copy
    assert 'caches.open(CACHE).then(c => c.match("nba_props.json"))' in html and "if (j && !D && !FRESH) apply(j);" in html
    assert 'if (FRESH && (Date.now() - iso(D.generated_at).getTime()) / 60000 > 10) out.push("Feed delayed");' in html
    assert "function prefetch() { refsLoad(); rolesLoad(); playerIndex(); }" in html and "setTimeout(prefetch, 1500)" in html
    # swaps rise in; Over / Under, the combo window and the Injuries switch slide their pills; Live's bars grow on entry
    assert html.count("swapIn(") >= 9 and '<span class="ou" role="group" aria-label="Side"><span class="pill2">' in html
    assert '<div class="seg cbw" role="group" aria-label="Games"><span class="pill2">' in html and ".lvin .lvbar i{" in html


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_slate_day_moves_on_once_the_night_is_over():
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "core.js").write_text(UI.JS_CORE)
    (d / "t.js").write_text("""
const C = require('./core.js'), D = ['2026-10-26', '2026-10-27'];
const g = (gid, date, state) => ({gid, date, state}), p = (gid, closed) => ({gid, closed});
const finals = [g('a', D[0], 'final'), g('b', D[0], 'final'), g('c', D[1], 'pregame')];
const late = [g('a', D[0], 'final'), g('b', D[0], 'live'), g('c', D[1], 'pregame')];
const props = [p('a', true), p('b', true), p('c', false)], noLines = [p('a', true), p('b', true)];
console.log(JSON.stringify([
  C.slateDay(D, finals, props, null), C.slateDay(D, finals, props, D[0]),      // the night is over, tomorrow has lines
  C.slateDay(D, late, props, D[0]), C.slateDay(D, late, props, null),          // a late game still on: tonight stays
  C.slateDay(D, finals, noLines, D[0]), C.slateDay(D, finals, noLines, null),  // over, but no lines for tomorrow yet
  C.slateDay(D, finals, props, '2026-10-25'), C.slateDay(D, finals, props, D[1])]));
""")
    out = json.loads(subprocess.run([NODE, str(d / "t.js")], capture_output=True, text=True, check=True, cwd=d).stdout)
    assert out == ["2026-10-27", "2026-10-27", "2026-10-26", "2026-10-26", "2026-10-26", "2026-10-26", "2026-10-27", "2026-10-27"]


def test_page_names_days_by_the_phones_date_and_finished_slates_by_name():
    html = UI.page()
    assert "ST.date = slateDay(D.dates, D.games, D.props, AUTO_DAY ? ST.date : null);" in html and "AUTO_DAY = false; if (ST.date !== b.dataset.date)" in html
    assert "if (HIDDEN_AT && Date.now() - HIDDEN_AT > 1800000) AUTO_DAY = true;" in html          # back after 30+ min: choose again
    assert 'const lab = dayName(ST.date);' in html and '"Yesterday"' in html and 'm === "live" && !liveNow ? "Results"' in html
    assert "<b>All games final</b>" in html and 'id="gonext"' in html


def test_a_slate_leaves_when_its_last_game_ends():
    # 7:30 PM ET, the night's one live game has just gone final (the other is postponed): the page moves on to the next
    # slate at once, the 6 AM ET hold notwithstanding; while that game is still on, the night stays (as built(NOW))
    final = [dict(g, status=3, status_text="Final") if g["gid"] == "G1" else g for g in SCHED]
    def final_box(gid):
        b = live_box(gid)
        return dict(b, gameStatus=3, gameStatusText="Final")
    over = built(NOW, final, final_box)
    assert over["dates"] == ["2026-10-27", "2026-10-28"] and {g["gid"] for g in over["games"]} == {"G3"}
    assert all(p["gid"] == "G3" for p in over["props"])
    # the schedule still says live but the box score says final: the box wins, the night is over
    lagging = built(NOW, SCHED, final_box)
    assert lagging["dates"][0] == "2026-10-27"
    assert built(NOW)["dates"][0] == GD                                            # still being played: the night stays


def test_projected_lineups_fill_in_for_who_is_out():
    # MIN, 10 games: A B C D E start; when E sat (3 games) F started; G and H come off the bench (G more minutes)
    box = lambda i, five, bench: (f"m{i}", f"2026-10-{10 + i}", "2026-27",
                                  {**{p: (1, 32.0) for p in five}, **{p: (0, m) for p, m in bench.items()}})
    sat = {7, 8, 9}
    mins = [box(i, [1, 2, 3, 4, 6] if i in sat else [1, 2, 3, 4, 5], {7: 20.0, 8: 12.0} if i in sat else {6: 18.0, 7: 20.0, 8: 12.0})
            for i in range(10)]
    boxes = {"MIN": mins, "WAS": [box(i, [11, 12, 13, 14, 15], {}) for i in range(10)], "NEW": [box(0, [21, 22, 23, 24, 25], {})]}
    roster = {"1": ["MIN", "Ay G", "G"], "2": ["MIN", "Bee F", "F"], "3": ["MIN", "Cee C", "C"], "4": ["MIN", "Dee G", "G"],
              "5": ["MIN", "Eee F", "F"], "6": ["MIN", "Eff F", "F"], "7": ["MIN", "Gee G", "G"], "8": ["MIN", "Aitch C", "C"],
              "11": ["WAS", "W1", "G"], "21": ["NEW", "N1", "G"]}
    D = "2026-10-27"
    official = {(D, 5): {"status": "Out"}, (D, 4): {"status": "Questionable"}, (D, 3): {"status": "Doubtful"}}
    games = [{"date_et": D, "home": "MIN", "away": "WAS"}, {"date_et": D, "home": "NEW", "away": "CHI"}]
    out = RS.projected_lineups(games, boxes, official, roster, {f"{D}|WAS": {"status": "Confirmed"}})
    assert set(out) == {f"{D}|MIN"}                          # WAS posted; NEW (1 game) and CHI (none) too early to project
    m = out[f"{D}|MIN"]
    five = [s[0] for s in m["starters"]]
    # E (Out) -> F, who started when E sat; C (Doubtful, never missed a start) -> H, the other center (over G's minutes)
    assert sorted(five) == [1, 2, 4, 6, 8] and m["subs"] == [[6, 5, "Eee F"], [8, 3, "Cee C"]]
    assert [s[2][:1] for s in m["starters"]] == ["G", "G", "F", "F", "C"]          # guards, then forwards, then centers
    assert dict((s[0], s[3]) for s in m["starters"])[4] == "Questionable" and m["status"] == "Projected"
    assert sorted(x[0] for x in m["missing"]) == [3, 5]
    # last season C sat twice for MIN and G started both: that evidence beats position (and E's 3 makes his the surer pick)
    full = {p: (1, 30.0) for p in (1, 2, 3, 4, 5)}
    ls = [("p0", "2026-03-01", "2025-26", full)] + [(f"p{i}", f"2026-03-0{i + 1}", "2025-26", {**{p: (1, 30.0) for p in (1, 2, 4, 5)}, 7: (1, 30.0)})
                                                    for i in (1, 2)]
    m2 = RS.projected_lineups(games, dict(boxes, MIN=ls + mins), official, roster, {})[f"{D}|MIN"]
    assert m2["subs"] == [[6, 5, "Eee F"], [7, 3, "Cee C"]]


def test_page_shows_projected_lineups():
    html = UI.page()
    assert 'proj = e.status === "Projected"' in html and '"PROJECTED"' in html and "<b>In for</b>" in html
    assert 'proj && INJ_S[st] ? ` · <em class="lq">' in html and "const miss = !proj && e.missing.length" in html


def test_injury_beneficiaries_open_their_page():
    html = UI.page()
    # every box under an injury is a button: his prop on the slate, else his player page (openPlayer via data-vp)
    assert 'return `<button class="ijb"${p ? ` data-id="${esc(p.id)}"` : ` data-vp="${m.pid}"`}>' in html
    assert 'e.target.closest(".pr[data-id],.ijb[data-id],[data-vp]")' in html


def test_player_page_has_last_seasons_window():
    html = UI.page()
    # 2026 · H2H · L5 · L10 · L20 · 2025: last season's games at the far right ("last" in windowed: every game before this season)
    assert '["l20", "L20"], ["last", String(+D.season.slice(0, 4) - 1)]];' in html
    assert 'if (win === "last") return logs.filter(function (l) { return seasonOf(l.date) !== season; });' in html


def test_matchup_shows_assist_and_rebound_zones_only_for_their_props():
    html = UI.page()
    assert 'const AST_M = new Set(["assists", "pts_ast", "reb_ast", "pra"]), REB_M = new Set(["rebounds", "pts_reb", "reb_ast", "pra"]);' in html
    assert """${AST_M.has(p.market) ? '<div class="shc wg" id="asc"></div>' : ""}${REB_M.has(p.market) ? '<div class="shc wg" id="rbc"></div>' : ""}""" in html
    assert 'if (AST_M.has(p.market)) zoneCard("ast");' in html and 'if (REB_M.has(p.market)) zoneCard("reb");' in html
    assert "fetch(`${dir}/${encodeURIComponent(s)}.json?t=${t}`)" in html and 'const pbpLoad = sideJson("pbp", new Map()), rebdLoad = sideJson("rebd", new Map());' in html
    # the shot chart only on props with points or threes in them: none on assists, rebounds or R+A
    assert 'const SHOT_M = new Set(["points", "threes", "pts_reb", "pts_ast", "pra"]);' in html
    assert """${SHOT_M.has(p.market) ? '<div class="shc" id="shc"></div>' : ""}""" in html and "if (SHOT_M.has(p.market)) shotLoad(D.season)" in html
    # the assists and rebounds courts: the shot chart's six zones (one shared drawing; a rebound by its miss's zone), his a
    # game shaded by his share against the league's, or the opponent's allowed a game shaded against the league and ranked;
    # a view switch redraws the court alone, each card keeping its own view
    assert "const zoneMarks = zs =>" in html and html.count("zoneMarks(") == 2 and html.count('<g class="shl">') == 2
    assert "fill: shFill(lt ? (mine[k] / tot - Lk[k] / lt) * 100 : null)" in html and "fill: shFill(la ? (a / la - 1) * 50 : null)" in html
    assert "const a = t[off + k] / t[0], la = Lk[k] / L.gp;" in html and "off = ast ? 1 : 1 + nz, L = j.league, Lk = L[kind];" in html
    assert "sub: ord(1 + all.filter(x => x[off + k] / x[0] < a).length)" in html and "const k = j.zones.indexOf(nm);" in html
    assert 'if (view) { const v = $(".zcv", el);' in html and 'astView: "player", rebView: "player"};' in html and 'vkey = kind + "View"' in html
    # rebounds: free throws (no zone on the court) as a line; the player's rings, 0-3 / 3-6 / 6-10 / 10+ ft from the hoop
    # (docs/rebd), shaded against the players with rebound lines; the defense view's missed threes against the league
    assert "NBA.com tracking · ${r[1]} boards ·" in html                 # the sample: early in a season a ring is a board or two
    # rebounds: the rings in both views, the opponent's from its opponents' rebounds against it (rd.teams; drawn in
    # test_rebound_rings_both_views)
    assert "Off missed free throws: " in html and "extra += r && r[1] ? rebRings(r, rd.avg, def ? rd.teams : null, p.opp)" in html
    assert "const r = rd && (def ? rd.teams && rd.teams[p.opp] : rd.players[String(p.pid)]);" in html and 'RD_FT = ["0–3", "3–6", "6–10", "10+"]' in html
    assert "if (def && t && t.length >= 1 + nz + 2 * Z.length && L.miss) {" in html
    assert "const m3 = x => (x[off + Z.length + 3] + x[off + Z.length + 4] + x[off + Z.length + 5]) / x[0], lg = (L.miss[3] + L.miss[4] + L.miss[5]) / L.gp;" in html
    # a rookie facing a team with few games this season still gets his own season, not last season's blank
    assert "MUP[key] = (t && t[0] >= 10) || (me(j) && !me(q)) ? D.season : prevSeason(D.season);" in html
