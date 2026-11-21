"""nba_quarters: each player's minutes and box score by quarter (docs/quarters/{pid}.json)."""
import json
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import nba_onoff as O
import nba_quarters as Q
from test_nba_onoff import A, B, START, TEAM, act, game


def _box(off=None):
    """The box score of test_nba_onoff.game() [(pid, team, starter, min, pts, reb, ast, fg3m)]; off: {pid: changes}."""
    mins = {1: 24, 2: 24, 3: 24, 4: 13, 5: 17, 6: 18, **{p: 24 for p in B}}
    stats = {1: (4, 0, 0, 1), 2: (0, 0, 1, 0), 3: (0, 1, 0, 0), 6: (2, 0, 0, 0), 11: (1, 0, 0, 0)}
    rows = []
    for p in A + B:
        r = [p, TEAM[p], 1 if p in START else 0, mins[p], *stats.get(p, (0, 0, 0, 0))]
        for i, v in ((off or {}).get(p) or {}).items():
            r[i] = v
        rows.append(tuple(r))
    return rows


def test_parse_splits_time_and_stats_by_period():
    per = {}
    O.parse(game(), TEAM, START, per)
    s = lambda p, q: dict(zip(("secs",) + O.STATS, per.get((p, q), [0.0] + [0] * len(O.STATS))))
    assert round(s(1, 1)["secs"]) == 720 and round(s(1, 2)["secs"]) == 720
    assert s(1, 1)["pts"] == 4 and s(1, 1)["fg3m"] == 1 and s(1, 1)["fga"] == 1 and s(1, 1)["fta"] == 1
    assert s(1, 2)["pts"] == 0 and s(1, 2)["fga"] == 1                          # Q2's miss goes to Q2
    assert round(s(5, 1)["secs"]) == 360 and round(s(5, 2)["secs"]) == 660      # out at 6:00 of Q1, in at 11:00 of Q2
    assert round(s(4, 1)["secs"]) == 720 and round(s(4, 2)["secs"]) == 60
    assert round(s(6, 1)["secs"]) == 360 and round(s(6, 2)["secs"]) == 720 and s(6, 1)["pts"] == 2
    assert s(2, 1)["ast"] == 1 and s(3, 1)["reb"] == 1 and s(3, 1)["oreb"] == 1 and s(11, 1)["pts"] == 1
    units, secs = O.parse(game(), TEAM, START)                                   # without it: as before
    assert round(secs[5]) == 1020
    assert all(round(sum(v[0] for (p, _), v in per.items() if p == q)) == round(secs[q]) for q in secs)


def test_split_checks_each_player_against_the_box_score():
    _, checks = Q.split(game(), _box())
    assert all(ok == 1 for ok, _ in checks.values()) and set(checks) == set(A + B)
    _, checks = Q.split(game(), _box({1: {4: 5}, 6: {3: 18.6}, 3: {5: 2}}))  # 1 scored 5, 6 played 18.6, 3 had 2 reb
    assert checks[1] == (0, "pts 4 v 5") and checks[6] == (0, "min 18.0 v 18.6") and checks[3] == (0, "reb 1 v 2")
    assert checks[2] == (1, None)
    _, checks = Q.split(game(), _box({6: {3: 18.4}}))                          # within half a minute
    assert checks[6] == (1, None)


def _stores():
    con = Q.connect(":memory:")
    mcon = sqlite3.connect(":memory:")
    mcon.execute("CREATE TABLE games (gid TEXT, season TEXT, date TEXT, home TEXT, away TEXT, home_pts INTEGER, away_pts INTEGER)")
    mcon.execute("CREATE TABLE player_games (gid TEXT, team TEXT, pid INTEGER, starter INTEGER, min REAL, pts REAL, reb REAL, "
                 "ast REAL, fg3m REAL)")
    for gid, season, d in (("g1", "2025-26", "2026-03-01"), ("g2", "2026-27", "2026-11-10"), ("g3", "2026-27", "2026-11-19"),
                           ("g4", "2026-27", "2026-11-12"), ("g5", "2024-25", "2025-03-01")):
        mcon.execute("INSERT INTO games VALUES (?, ?, ?, 'AAA', 'BBB', 100, 90)", (gid, season, d))
        box = _box({1: {4: 9}} if gid == "g2" else None)                       # g2: 1's box score says 9 points
        mcon.executemany("INSERT INTO player_games VALUES (?,?,?,?,?,?,?,?,?)",
                         [(gid, t, p, st, mn, *x) for p, t, st, mn, *x in box])
    mcon.execute("INSERT INTO games VALUES ('g6', '2026-27', '2026-11-20', 'AAA', 'BBB', NULL, NULL)")   # not final
    return con, mcon


def test_fetch_stores_each_final_game_once_and_build_gives_four_quarters():
    con, mcon = _stores()
    asked = []
    feeds = {"g1": game(), "g2": game(), "g4": None,                              # g4: no feed, 9 days ago: let go
             "g3": [a for a in game() if a["actionType"] != "game"][:-2]}         # g3: not to its end, 1 day ago: wait
    get = lambda gid: (asked.append(gid), feeds[gid])[1]
    assert Q.fetch(con, mcon, ("2025-26", "2026-27"), get=get, today="2026-11-21") == (3, 1, 1)
    assert sorted(asked) == ["g1", "g2", "g3", "g4"]                              # not g5 (another season) or g6
    assert con.execute("SELECT why FROM games WHERE gid = 'g4'").fetchone() == ("no full feed",)
    asked.clear()
    assert Q.fetch(con, mcon, ("2025-26", "2026-27"), get=get, today="2026-11-21") == (0, 1, 0)
    assert asked == ["g3"]                                                        # only the one still waiting
    docs = Q.build(con, ("2025-26", "2026-27"))
    d1 = docs[1]
    assert d1["cols"] == list(Q.COLS) and set(d1["games"]) == {"g1"}              # g2 is off his box score
    assert d1["games"]["g1"] == [[12.0, 4, 0, 0, 1, 1, 1, 1], [12.0, 0, 0, 0, 0, 1, 0, 0], [0.0] + [0] * 7, [0.0] + [0] * 7]
    assert set(docs[6]["games"]) == {"g1", "g2"} and docs[6]["games"]["g2"][0][:2] == [6.0, 2]
    assert docs[5]["games"]["g1"][1][0] == 11.0
    assert set(Q.build(con, ("2026-27",))[6]["games"]) == {"g2"}                  # a season's games only


def test_an_unreadable_game_is_kept_off():
    con, mcon = _stores()
    feeds = {"g1": game(), "g2": game(), "g3": game(), "g4": game()}
    feeds["g1"] = [act(1, 1, "PT12M00.00S", "period", sub="start"), act(2, 1, "PT00M00.00S", "period", sub="end"),
                   act(3, 2, "PT11M00.00S", "2pt", 1, shotResult="Made"), act(4, 2, "PT00M00.00S", "game", sub="end")]
    Q.fetch(con, mcon, ("2025-26", "2026-27"), get=feeds.get, today="2026-11-21")
    assert con.execute("SELECT ok FROM games WHERE gid = 'g1'").fetchone() == (0,)
    assert "g1" not in Q.build(con, ("2025-26", "2026-27"))[1]["games"]


def test_write_only_rewrites_files_that_changed():
    d = pathlib.Path(tempfile.mkdtemp())
    docs = {1: {"pid": 1, "cols": ["min"], "games": {"g1": [[1.0], [0.0], [0.0], [0.0]]}}, 2: {"pid": 2, "cols": ["min"], "games": {}}}
    assert Q.write(d, docs) == 2
    assert json.loads((d / "1.json").read_text())["games"]["g1"][0] == [1.0]
    assert Q.write(d, docs) == 0
    docs[2]["games"]["g9"] = [[3.0], [0.0], [0.0], [0.0]]
    assert Q.write(d, docs) == 1 and not list(d.glob(".*.tmp"))


NODE = __import__("shutil").which("node")


@__import__("pytest").mark.skipif(NODE is None, reason="node not installed")
def test_quarter_logs_swap_in_a_quarter():
    import subprocess
    import nba_research_ui as UI
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "core.js").write_text(UI.JS_CORE)
    (d / "t.js").write_text("""const C = require('./core.js');
const logs = [{date: '2026-11-01', gid: 'a', starter: 1, min: 34.2, pts: 30, reb: 8, ast: 5, fg3m: 4, fga: 20, fg3a: 9, fta: 6, margin: 7, usg: 31, pot_ast: 9, reb_ch: 14},
              {date: '2026-11-03', gid: 'b', starter: 1, min: 30.0, pts: 20, reb: 4, ast: 2, fg3m: 1, fga: 15, fg3a: 4, fta: 2, margin: -3, usg: 25, pot_ast: 4, reb_ch: 8},
              {date: '2026-11-05', gid: 'c', starter: 0, min: 20.0, pts: 9, reb: 2, ast: 1, fg3m: 0, fga: 8, fg3a: 1, fta: 1, margin: 20, usg: 18, pot_ast: 2, reb_ch: 4}];
const doc = {cols: ['min', 'pts', 'reb', 'ast', 'fg3m', 'fga', 'fg3a', 'fta'],
             games: {a: [[9.5, 10, 2, 1, 2, 6, 3, 1], [7.0, 5, 2, 2, 0, 4, 2, 2], [10.2, 11, 3, 1, 2, 6, 3, 3], [7.5, 4, 1, 1, 0, 4, 1, 0]],
                     c: [[0.0, 0, 0, 0, 0, 0, 0, 0], [8.1, 5, 1, 0, 0, 4, 1, 1], [0.0, 0, 0, 0, 0, 0, 0, 0], [11.9, 4, 1, 1, 0, 4, 0, 0]]}};
const q1 = C.quarterLogs(logs, doc, 1), q4 = C.quarterLogs(logs, doc, 4);
console.log(JSON.stringify({q1: q1, q4: q4.map(l => [l.gid, l.min, l.pts]), pts1: q1.map(l => C.statValue(l, 'pra')), orig: logs[0].pts,
  lines: [24.5, 8.5, 2.5, 1.5, 35.5, 0.5].map(C.quarterLine), none: C.quarterLogs(logs, null, 1).length}));""")
    out = json.loads(subprocess.run([NODE, str(d / "t.js")], capture_output=True, text=True, check=True, cwd=d).stdout)
    a = out["q1"][0]
    assert [l["gid"] for l in out["q1"]] == ["a", "c"]                            # b has no quarter file row: left out
    assert (a["min"], a["pts"], a["reb"], a["ast"], a["fg3m"], a["fga"], a["fg3a"], a["fta"]) == (9.5, 10, 2, 1, 2, 6, 3, 1)
    assert (a["usg"], a["pot_ast"], a["reb_ch"], a["q"]) == (None, None, None, 1)
    assert (a["date"], a["starter"], a["margin"]) == ("2026-11-01", 1, 7)        # the game's own facts kept
    assert out["q1"][1]["min"] == 0.0 and out["q1"][1]["pts"] == 0                # sat the quarter: zeros, still a game
    assert out["q4"] == [["a", 7.5, 4], ["c", 11.9, 4]] and out["pts1"] == [13, 0] and out["orig"] == 30
    assert out["lines"] == [6.5, 2.5, 0.5, 0.5, 8.5, 0.5] and out["none"] == 0


def test_quarter_filter_on_the_player_page():
    import nba_research_ui as UI
    html = UI.page()
    assert 'const QTRS = [[0, "Full"], [1, "1Q"], [2, "2Q"], [3, "3Q"], [4, "4Q"]];' in html
    assert '${SPORT === "nba" ? `<div class="qrow"><div class="wcap qcap" id="qcap" role="group" aria-label="Quarter">' in html
    assert "fetch(`quarters/${pid}.json?t=${t}`)" in html
    assert 'PX = {p: p, g: g, full: logs, logs: DT.q ? quarterLogs(logs, QD.get(p.pid), DT.q) : logs,' in html
    assert "if (!was && q) { DT.qFrom = DT.line; DT.line = quarterLine(DT.line); }" in html
    assert "if (was && !q) { if (DT.qFrom !== null) DT.line = DT.qFrom; DT.qFrom = null; }" in html
    assert "if (!was !== !q) Object.assign(DT, {ranges: {}, open: {}, ovs: []});" in html
    assert "PX.logs = q ? quarterLogs(PX.full, QD.get(p.pid), q) : PX.full;" in html
    assert "if (fresh && same && DT.q) { DT.qFrom = DT.line; DT.line = quarterLine(DT.line); }" in html
    assert "open: {}, ovs: [], q: null, qFrom: null});" in html                  # a new player starts on the full game
    assert "else if (DT.q) { $(\"#pproj\").innerHTML = \"\"; $(\"#pbk\").innerHTML = " in html
    assert '$("#pf", pg).onclick = () => playerFilters(p, PX.logs, without);' in html
    assert ".qcap .wc[aria-pressed=\"true\"] i{color:#fff}" in html
