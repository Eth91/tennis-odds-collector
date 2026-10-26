"""The Pickz NBA prop research feed (nba_research.py) and page (nba_research_ui.py): derived statistics, the payload
built from synthetic stores (books + alternate rungs, logs, official report vs news, absences, related props, live
and postponed games, stale books, engine flags), the page's JS against the Python, and the page's script syntax."""
import datetime as dt
import json
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
    return RS.build(now=NOW, sched=SCHED, lines=d / "lines.sqlite", news=d / "news.sqlite", shadow=d / "shadow.sqlite",
                    matchup=d / "matchup.sqlite", index=d / "index.json", box_get=live_box)


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
    # chart bars show their game on tap (a <title> only appears on hover); the odds pills switch Over / Under
    assert "barTip(" in html and "data-ps=" in html


def test_board_links_the_page():
    import nba_board as B
    assert 'href="nba_props.html"' in B.html({"record": None, "slates": [], "retracted": [], "offcard": []})


def test_write_is_atomic(payload):
    d = pathlib.Path(tempfile.mkdtemp())
    RS.write(d, payload)
    assert json.loads((d / "nba_props.json").read_text())["props"] and (d / "nba_props.html").read_text().startswith("<!doctype")
    assert not list(d.glob(".*.tmp"))
