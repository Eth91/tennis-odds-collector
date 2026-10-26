"""The Pickz NBA prop research feed (nba_research.py) and page (nba_research_ui.py): derived statistics, the payload
built from synthetic stores (books + alternate rungs, logs, official report vs news, absences, related props, live
and postponed games, stale books, engine flags), the page's JS against the Python, and the page's script syntax."""
import datetime as dt
import inspect
import json
import math
import pathlib
import random
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
        (*new, GD, "SAC@PHX", "PHX", 3, "Jusuf Nurkic", "Out", "Injury/Illness - Knee"),     # Allen dropped off: cleared
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


@pytest.fixture(scope="module")
def payload():
    d = pathlib.Path(tempfile.mkdtemp())
    stores(d)
    tr = sqlite3.connect(d / "tracking.sqlite")
    tr.execute("CREATE TABLE tracking (date TEXT, player_id INTEGER, potential_ast REAL, ast_trk REAL, passes REAL, "
               "secondary_ast REAL, ft_ast REAL, reb_chances REAL, oreb_chances REAL, dreb_chances REAL, reb_trk REAL)")
    tr.execute("INSERT INTO tracking (date, player_id, potential_ast, reb_chances) VALUES ('2026-09-01', 1, 14, 9)")
    tr.execute("INSERT INTO tracking (date, player_id, potential_ast, reb_chances) VALUES ('2026-09-02', 1, 11, NULL)")
    tr.commit(); tr.close()
    return RS.build(now=NOW, sched=SCHED, lines=d / "lines.sqlite", news=d / "news.sqlite", shadow=d / "shadow.sqlite",
                    matchup=d / "matchup.sqlite", index=d / "index.json", box_get=live_box, tracking=d / "tracking.sqlite")


def test_payload_props_and_books(payload):
    ids = {p["id"] for p in payload["props"]}
    assert ids == {"G1|1|points", "G1|1|assists", "G1|2|points"}, ids          # no steals, no out-of-range game
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
    ir = payload["inj_report"][f"{GD}|PHX"]                # the Injuries view: the traded-in 8 has no PHX game to read
    assert ir["listed"] and [(e["pid"], e["missed"], e["starter"]) for e in ir["players"]] == [(8, 0, True), (3, 10, True)]


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
out.z = [C.zscore(7, 10, 0.5), C.zscore(0, 0, 0.5), C.zscore(3, 3, null)];
out.sv = C.sortProps(props, 'value', 'desc', () => [], 'over').map(p => p.id);
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
    assert out["f2"] == ["G1|2|points"]                                        # search
    assert out["f3"] == ["G1|1|points"]                                        # line >= 12 and over price <= -110
    assert out["s1"] == ["G1|1|assists", "G1|2|points", "G1|1|points"]          # ascending line
    assert len(out["s2"]) == 3                                                 # no logs: all missing, stable order
    assert out["s2"] == [p["id"] for p in payload["props"]]
    assert out["am"] == ["-115", "+150", "—", 1667]
    homes = sum(1 for l in logs if l["home"] == 1)
    assert out["fl"] == [homes, 30 - homes, 10, 0]                              # home; away starters; without Nurkic; bench
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


def test_page_controls_work_on_iphone():
    html = UI.page()
    # iOS Safari can't drag the thumb of a range input stacked under another, so the dual sliders are pointer-event widgets
    assert 'type="range"' not in html and "dualRange(" in html and "touch-action:pan-y" in html
    # chart bars show their game on tap (a <title> only appears on hover); the book prices switch Over / Under
    assert "barTip(" in html and "data-ps=" in html
    # the reference layout: Trends tab, game cards, a floating Props / Markets / Injuries bar, a books table
    assert all(k in html for k in ('trends: "Trends"', 'class="gc"', 'data-view="', '["injuries", "Injuries"]', 'id="pbk"'))
    # the Watchlist is a filter now (an old #view=watch link lands on it); a teammate named in an injury read opens his prop
    assert '["watch", "Watchlist"]' not in html and 'Object.assign(ST, {view: "props", watch: "1"})' in html and "data-wl=" in html
    assert ".ijm[data-id]" in html and "function injView(" in html and 'ST.view === "injuries"' in html
    # motion runs as Web Animations with a timer fallback, and nothing is fetched from a font CDN
    assert ".animate([" in html and "setTimeout(done" in html and "fonts.googleapis" not in html
    # every range chip but Margin draws its stat on the chart as white outline boxes (Margin can be negative: filter only)
    assert ('const OVL = {min: "min", fga: "FGA", fg3a: "3PTA", fta: "FTA", usg: "usage %", pot_ast: "potential assists", '
            'reb_ch: "rebound chances"}') in html and "l[ov]" in html
    # the adjustable filters come first; potential assists / rebound chances only on the props they bear on
    assert '["min", "fga", "fg3a", "fta", "usg", "pot_ast", "reb_ch"].forEach(rchip)' in html
    assert html.index('.forEach(rchip);') < html.index("if (c.dvp_rank) chips.push(") and 'const MORE_R = ["margin"];' in html
    assert 'pot_ast: ["assists", "pra", "pts_ast", "reb_ast"], reb_ch: ["rebounds", "pra", "pts_reb", "reb_ast"]' in html
    # no explanatory prose: notes are status only, empty states are titles only
    import re
    notes = re.findall(r'class="note"[^>]*>([^<$]*)', html)
    assert all(n.strip() in ("Loading…", "") or n.startswith("Couldn") for n in notes), notes
    assert not re.search(r'<div class="empty"><b>[^<]+</b>[A-Za-z]', html)
    # research+: fair price / VALUE, honest hit-rate boxes, Trends + Injuries tabs, line history, books that disagree
    assert all(k in html for k in ("fairAt(", "<i>VALUE</i>", "hbox(", 'injury: "Injuries"', "histChart(", "freshOut(", 'class="df"'))
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
    assert [e["pid"] for e in phx["players"]] == [30, 10, 14, 99, 15]          # Out by minutes, then Questionable
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
