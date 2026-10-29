"""The NFL side of Pickz: nfl_common, nfl_stats, nfl_research and the page's NFL switch."""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import shutil
import sqlite3
import subprocess
import tempfile

import pytest

import nba_lines
import nba_research_ui as UI
import nfl_common as C
import nfl_research as R
import nfl_stats as NS

NODE = shutil.which("node")
COLS = NS.LOG_COLS


# ── nfl_common ────────────────────────────────────────────────────────────────────────────────────────────────
def test_ids_and_teams():
    assert C.pid_of("00-0039732") == 39732 and C.gsis_of(39732) == "00-0039732"
    assert C.pid_of("") is None and C.pid_of("39732") is None
    assert C.team("LA") == "LAR" and C.team("WSH") == "WAS" and C.team("gb") == "GB" and C.team("XYZ") is None
    assert C.team_of_name("Green Bay Packers") == "GB" and C.team_of_name("LA Rams") == "LAR" and C.team_of_name("SF 49ers") == "SF"
    assert C.fold("D.J. Moore") == C.fold("DJ Moore") == "dj moore" and C.fold("Ja'Kobi Lane") == "jakobi lane"


def _roster(**kw):
    return {pid: {"name": n, "team": t, "football_name": fb} for pid, (n, t, fb) in kw.items()}


def test_resolver_scoped_and_unique():
    r = C.Resolver({1: {"name": "Josh Allen", "team": "BUF", "football_name": ""},
                    2: {"name": "Josh Allen", "team": "JAX", "football_name": ""},          # the defender, another team
                    3: {"name": "John Metchie III", "team": "CAR", "football_name": ""},
                    4: {"name": "Andrew Ogletree", "team": "IND", "football_name": "Drew"},
                    5: {"name": "Mike Williams", "team": "NYJ", "football_name": ""},
                    6: {"name": "Malik Williams", "team": "NYJ", "football_name": ""}})
    assert r.resolve("Josh Allen", ("BAL", "BUF")) == 1          # scoped to the game's two teams
    assert r.resolve("Josh Allen", ("BUF", "JAX")) is None        # two of them in scope: never guessed
    assert r.resolve("John Metchie", ("CAR", "GB")) == 3          # the suffix is optional
    assert r.resolve("Drew Ogletree", ("IND", "TEN")) == 4        # the name he goes by
    assert r.resolve("M. Williams", ("NYJ", "LV")) is None         # an initial two players share
    assert r.resolve("Nobody Here", ("NYJ", "LV")) is None


def test_current_week_moves_on_after_the_last_game():
    g = lambda gid, wk, utc, hs=None: {"gid": gid, "season": 2026, "week": wk, "utc": utc, "home_score": hs}
    s = [g("a", 7, "2026-10-26T00:15:00", 20), g("b", 8, "2026-10-30T00:15:00"), g("c", 8, "2026-11-03T01:15:00"),
         g("d", 9, "2026-11-06T01:15:00")]
    at = lambda t: C.current_week(s, dt.datetime.fromisoformat(t).replace(tzinfo=dt.timezone.utc))
    assert at("2026-10-29T12:00:00") == (2026, 8)
    assert at("2026-11-03T04:00:00") == (2026, 8)             # Monday night's game still on (4 h after kickoff)
    assert at("2026-11-03T06:00:00") == (2026, 9)


# ── nfl_stats: the play by play ────────────────────────────────────────────────────────────────────────────────
PBP_COLS = ["season_type", "play_type", "two_point_attempt", "aborted_play", "game_id", "posteam", "defteam", "yardline_100",
            "yards_gained", "pass_attempt", "qb_dropback", "wp", "qtr", "game_seconds_remaining", "passer_player_id",
            "receiver_player_id", "rusher_player_id", "sack", "complete_pass", "air_yards", "pass_location", "rush_attempt",
            "qb_scramble", "run_location", "run_gap", "touchdown", "td_player_id"]


def _play(**kw):
    base = {c: "" for c in PBP_COLS}
    base.update(season_type="REG", game_id="2026_01_A_B", posteam="GB", defteam="CHI", wp=".5", qtr="1",
                two_point_attempt="0", aborted_play="0", sack="0", touchdown="0", qb_scramble="0")
    base.update({k: str(v) for k, v in kw.items()})
    return [base[c] for c in PBP_COLS]


def test_from_pbp(monkeypatch):
    P, W, B = "00-0000001", "00-0000002", "00-0000003"
    plays = [
        _play(play_type="pass", pass_attempt=1, qb_dropback=1, passer_player_id=P, receiver_player_id=W, complete_pass=1,
              yards_gained=31, air_yards=22, pass_location="left", yardline_100=60, game_seconds_remaining=3500),
        _play(play_type="pass", pass_attempt=1, qb_dropback=1, passer_player_id=P, receiver_player_id=W, complete_pass=1,
              yards_gained=12, air_yards=8, pass_location="middle", yardline_100=15, game_seconds_remaining=3470),
        _play(play_type="pass", pass_attempt=1, qb_dropback=1, passer_player_id=P, receiver_player_id=W, complete_pass=0,
              yards_gained=0, air_yards=25, pass_location="right", yardline_100=30, game_seconds_remaining=3440),
        _play(play_type="run", rush_attempt=1, rusher_player_id=B, yards_gained=7, run_location="left", run_gap="tackle",
              yardline_100=18, game_seconds_remaining=3400),
        _play(play_type="run", rush_attempt=1, rusher_player_id=B, yards_gained=3, run_location="middle", yardline_100=11,
              touchdown=1, td_player_id=B, game_seconds_remaining=3370),
        _play(play_type="pass", pass_attempt=1, qb_dropback=1, passer_player_id=P, receiver_player_id=W, complete_pass=1,
              yards_gained=50, two_point_attempt=1),                                   # a two-point try: none of it counts
        _play(play_type="run", rush_attempt=1, rusher_player_id=B, yards_gained=40, qb_scramble=0, season_type="PRE"),
    ]
    monkeypatch.setattr(NS, "pbp_rows", lambda s, c: ({k: i for i, k in enumerate(PBP_COLS)}, iter(plays)))
    per, team, rdir, tree, extra = NS.from_pbp(2026, 2026)
    g = "2026_01_A_B"
    assert per[(1, g)]["long_comp"] == 31
    assert per[(2, g)]["long_rec"] == 31 and per[(2, g)]["rz_tgt"] == 1 and per[(2, g)]["deep_tgt"] == 2
    assert per[(3, g)]["long_rush"] == 7 and per[(3, g)]["rz_rush"] == 2
    assert team[("GB", g)]["plays"] == 5 and team[("GB", g)]["pass"] == 3 and team[("GB", g)]["rush"] == 2
    assert rdir[("p", "3")]["lt"] == [1, 7, 0] and rdir[("p", "3")]["m"] == [1, 3, 1] and rdir[("d", "CHI")]["lt"] == [1, 7, 0]
    assert tree[2]["dpl"] == [1, 1, 31] and tree[2]["shm"] == [1, 1, 12] and tree[2]["dpr"] == [1, 0, 0]


# ── nfl_research ───────────────────────────────────────────────────────────────────────────────────────────────
def _log(**kw):
    base = {c: 0 for c in COLS}
    base.update(date="2026-09-14", gid="2026_01_X_Y", week=1, team="GB", opp="CHI", home=1, margin=7, rest=7, spr=-3,
                tot=44, snaps=50, snap_pct=80, long_comp=None, long_rush=None, long_rec=None, tgt_share=None, air_share=None,
                rush_share=None)
    base.update(kw)
    return [base[c] for c in COLS]


def test_dvp_sums_a_group_and_takes_its_longest():
    logs = {1: [_log(gid="g1", opp="CHI", rec_yds=60, long_rec=30, rec=4), _log(gid="g2", opp="DET", rec_yds=20, long_rec=9, rec=2, date="2026-09-21")],
            2: [_log(gid="g1", opp="CHI", rec_yds=40, long_rec=35, rec=3), _log(gid="g2", opp="DET", rec_yds=10, long_rec=10, rec=1, date="2026-09-21")]}
    pos = {1: "WR", 2: "WR"}
    t = R.dvp_tables(logs, pos, 2026)
    assert t["val"]["WR"]["rec_yds"] == {"CHI": 100.0, "DET": 30.0}
    assert t["val"]["WR"]["long_rec"] == {"CHI": 35.0, "DET": 10.0}            # the group's longest, not a sum
    assert t["dvp"]["WR"]["rec_yds"] == {"DET": 1, "CHI": 2}                    # 1 = allowed the least
    assert t["n"] == {"CHI": 1, "DET": 1}
    assert R.dvp_tables(logs, pos, 2026, before="2026-09-20")["n"] == {"CHI": 1}   # point in time


def test_box_stats_from_espn():
    summ = {"boxscore": {"players": [{"statistics": [
        {"name": "passing", "labels": ["C/ATT", "YDS", "AVG", "TD", "INT"], "athletes": [{"athlete": {"id": "11"}, "stats": ["21/30", "254", "8.5", "2", "1"]}]},
        {"name": "rushing", "labels": ["CAR", "YDS", "AVG", "TD", "LONG"], "athletes": [{"athlete": {"id": "22"}, "stats": ["14", "71", "5.1", "1", "19"]}]},
        {"name": "receiving", "labels": ["REC", "YDS", "AVG", "TD", "LONG", "TGTS"], "athletes": [{"athlete": {"id": "22"}, "stats": ["3", "18", "6", "0", "9", "4"]},
                                                                                              {"athlete": {"id": "99"}, "stats": ["1", "5", "5", "0", "5", "1"]}]},
        {"name": "kicking", "labels": ["FG", "PCT", "LONG", "XP", "PTS"], "athletes": [{"athlete": {"id": "33"}, "stats": ["2/3", "66.7", "48", "3/3", "9"]}]},
        {"name": "kickReturns", "labels": ["NO", "YDS", "AVG", "LONG", "TD"], "athletes": [{"athlete": {"id": "22"}, "stats": ["1", "99", "99", "99", "1"]}]}]}]}}
    s = R.box_stats(summ, {"11": 1, "22": 2, "33": 3})
    assert s[1]["pass_comp"] == 21 and s[1]["pass_att"] == 30 and s[1]["pass_yds"] == 254 and s[1]["pass_int"] == 1
    assert s[2]["rush_yds"] == 71 and s[2]["rec"] == 3 and s[2]["targets"] == 4 and s[2]["long_rec"] == 9 and s[2]["td"] == 2
    assert R.stat_value(s[2], "rush_rec_yds") == 89 and R.stat_value(s[2], "anytime_td") == 2
    assert s[3]["fg_made"] == 2 and s[3]["kick_pts"] == 9
    assert 99 not in s and len(s) == 3                                         # an athlete off the roster map is left out


def test_injuries_official_over_espn():
    players = {1: {"espn": "101"}, 2: {"espn": "102"}, 3: {"espn": "103"}}
    j = {"injuries": [{"injuries": [
        {"athlete": {"id": "101"}, "status": "Questionable", "date": "2026-10-28T20:00Z", "shortComment": "limited Wednesday", "details": {"type": "Hamstring"}},
        {"athlete": {"id": "102"}, "status": "Injured Reserve", "date": "2026-10-01T20:00Z", "details": {"type": "Knee", "side": "Left"}},
        {"athlete": {"id": "103"}, "status": "Questionable", "date": "2026-10-28T20:00Z", "details": {}}]}]}
    get = lambda u: json.dumps(j).encode()
    with tempfile.TemporaryDirectory() as d:
        C.CACHE = pathlib.Path(d)
        out = R.injuries(players, get, official={3: {"status": "Out", "reason": "Ankle", "practice": "Did Not Participate"}})
    assert out[1]["status"] == "Questionable" and out[1]["news"][0]["headline"] == "limited Wednesday"
    assert out[2]["status"] == "Out" and out[2]["long"] and out[2]["reason"] == "Left Knee"
    assert out[3]["status"] == "Out" and out[3]["practice"] == "Did Not Participate"


def test_live_state_maps_espn_by_teams():
    games = [{"gid": "2026_08_CAR_GB", "date": "2026-10-29", "away": "CAR", "home": "GB"},
             {"gid": "2026_08_LAC_LA", "date": "2026-11-01", "away": "LAC", "home": "LAR"}]
    sb = {"events": [
        {"id": "9", "competitions": [{"competitors": [{"homeAway": "away", "score": "13", "team": {"abbreviation": "CAR"}},
                                                       {"homeAway": "home", "score": "17", "team": {"abbreviation": "GB"}}],
                                       "status": {"period": 3, "clock": 501, "type": {"state": "in", "name": "STATUS_IN_PROGRESS", "shortDetail": "8:21 - 3rd"}}}]},
        {"id": "10", "competitions": [{"competitors": [{"homeAway": "away", "team": {"abbreviation": "LAC"}},
                                                        {"homeAway": "home", "team": {"abbreviation": "LA"}}],
                                        "status": {"type": {"state": "pre", "name": "STATUS_SCHEDULED"}}}]}]}
    with tempfile.TemporaryDirectory() as d:
        C.CACHE = pathlib.Path(d)
        out = R.live_state(games, lambda u: json.dumps(sb).encode())
    a = out["2026_08_CAR_GB"]
    assert a["state"] == "live" and a["score"] == [13, 17] and a["espn"] == "9" and a["frac"] == round((2 * 900 + 399) / 3600, 3)
    assert out["2026_08_LAC_LA"]["state"] == "pregame" and out["2026_08_LAC_LA"]["espn"] == "10"   # LA = LAR


def test_gains_reads_the_games_without_him():
    gl = [(f"2026-09-{d:02d}", f"g{i}") for i, d in enumerate((7, 14, 21, 28, 5), 1)]
    gl[-1] = ("2026-10-05", "g5")
    star = [_log(gid=g, date=d, targets=10) for d, g in gl[:3]]                  # he played g1-g3, out g4-g5
    mate = [_log(gid=g, date=d, targets=t) for (d, g), t in zip(gl, (3, 4, 3, 9, 8))]
    logs, pos = {1: star, 2: mate}, {1: "WR", 2: "WR"}
    out = R.gains(logs, pos, "GB", {"g1", "g2", "g3"}, gl, 1)
    assert out == [{"pid": 2, "gain": round(8.5 - 10 / 3, 1), "mpg": 8.5, "n": 2}]
    assert R.gains(logs, pos, "GB", {"g1", "g2", "g3", "g4"}, gl, 1) == []      # one game without him: not read


def test_vs_rows_quarterbacks_who_threw():
    logs = {1: [_log(gid="g1", opp="CHI", pass_att=30, pass_yds=250)], 2: [_log(gid="g1", opp="CHI", pass_att=0, rush_att=2, rush_yds=-3)],
            3: [_log(gid="g1", opp="CHI", targets=5, rec=3, rec_yds=40)], 4: [_log(gid="g1", opp="CHI", snaps=10)]}
    out = R.vs_rows(logs, {1: "QB", 2: "QB", 3: "WR", 4: "WR"}, ["CHI"], {1: "A", 2: "B", 3: "C", 4: "D"})
    assert sorted(r[3] for r in out["CHI"]) == [1, 3]                          # the QB who ran only, the WR who never touched it: out


# ── the whole build, small ─────────────────────────────────────────────────────────────────────────────────────
def _stats_db(path):
    con = sqlite3.connect(path)
    con.executescript(NS.DDL)
    rows = []
    for k, (d, gid, opp, home) in enumerate([("2025-11-02", "2025_09_GB_CHI", "CHI", 0), ("2026-09-13", "2026_01_GB_CHI", "CHI", 1),
                                            ("2026-09-20", "2026_02_DET_GB", "DET", 1), ("2026-09-27", "2026_03_GB_MIN", "MIN", 0)]):
        s = 2025 if d < "2026" else 2026
        rows.append((s, 100, "WR") + tuple(_log(date=d, gid=gid, opp=opp, home=home, targets=8 + k, rec=5 + k, rec_yds=60 + 10 * k,
                                                  long_rec=20 + k, td=k % 2, snap_pct=85)))
        rows.append((s, 200, "QB") + tuple(_log(date=d, gid=gid, opp=opp, home=home, pass_att=30, pass_yds=240 + k, snap_pct=100)))
        if k < 3:                                                           # the backup back, out tonight, missed week 3
            rows.append((s, 300, "RB") + tuple(_log(date=d, gid=gid, opp=opp, home=home, rush_att=12, rush_yds=50)))
        rows.append((s, 400, "LB") + tuple(_log(date=d, gid=gid, opp=opp, home=home, tackles=6)))
    con.executemany(f"INSERT INTO logs VALUES ({','.join('?' * (3 + len(COLS)))})", rows)
    for pid, n, pos, espn in ((100, "Wes Wideout", "WR", "1001"), (200, "Quinn Arm", "QB", "2001"), (300, "Ron Back", "RB", "3001"),
                              (400, "Lou Backer", "LB", "4001")):
        con.execute("INSERT INTO players VALUES (?,?,?,?,?,?,?,?,?)", (pid, n, "GB", pos, None, espn, None, None, "ACT"))
        con.execute("INSERT INTO names VALUES (?,?,?)", (pid, n, pos))
    con.execute("INSERT INTO meta VALUES ('meta', ?)", (json.dumps({"built_at": "2026-10-29T06:00:00+00:00"}),))
    con.commit()
    con.close()


def _lines_db(path, gid, tip):
    con = sqlite3.connect(path)
    con.executescript(nba_lines.DDL)
    at = "2026-10-29T12:00:00"
    for book, o, u in (("fd", 1.87, 1.95), ("dk", 1.91, 1.91)):
        for side, odds in (("over", o), ("under", u)):
            con.execute("INSERT INTO board VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (book, at, gid, tip, "e", "GB", "CHI", 100, "Wes Wideout", "rec_yds", 64.5, side, odds))
            con.execute("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)", (at, book, gid, tip, 100, "Wes Wideout", "rec_yds", 64.5, side, odds))
    con.execute("INSERT INTO board VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", ("fd", at, gid, tip, "e", "GB", "CHI", 100, "Wes Wideout", "anytime_td", 0.5, "over", 2.4))
    con.execute("INSERT INTO game_lines VALUES (?,?,?,?,?,?,?,?)", (at, "fd", gid, tip, "spread", "home", -6.5, 1.91))
    con.commit()
    con.close()


def test_build_small(monkeypatch, tmp_path):
    gid, tip = "2026_08_CHI_GB", "2026-11-01T17:00:00"
    sched = [{"gid": "2026_01_GB_CHI", "season": 2026, "week": 1, "type": "REG", "date": "2026-09-13", "utc": "2026-09-13T17:00:00",
              "away": "CHI", "home": "GB", "home_score": 20, "away_score": 13, "spread": 3, "total": 44, "home_rest": 7, "away_rest": 7},
             {"gid": gid, "season": 2026, "week": 8, "type": "REG", "date": "2026-11-01", "utc": tip, "away": "CHI", "home": "GB",
              "home_score": None, "away_score": None, "spread": 6.5, "total": 45.5, "home_rest": 4, "away_rest": 13, "roof": "outdoors",
              "surface": "grass", "stadium": "Lambeau Field", "div": True}]
    _stats_db(tmp_path / "s.sqlite")
    _lines_db(tmp_path / "l.sqlite", gid, tip)
    monkeypatch.setattr(C, "CACHE", tmp_path / "cache")
    inj = {"injuries": [{"injuries": [{"athlete": {"id": "3001"}, "status": "Out", "date": "2026-10-30T20:00Z", "details": {"type": "Ankle"}},
                                      {"athlete": {"id": "4001"}, "status": "Out", "date": "2026-10-30T20:00Z", "details": {"type": "Knee"}}]}]}
    def get(url):
        if url.endswith("/injuries"):
            return json.dumps(inj).encode()
        if "depthcharts" in url:
            return json.dumps({"depthchart": [{"positions": {"wr1": {"athletes": [{"id": "1001"}]}, "qb": {"athletes": [{"id": "2001"}]}}}]}).encode()
        return json.dumps({"events": []}).encode()
    pl = R.build(now=dt.datetime(2026, 10, 29, 12, tzinfo=dt.timezone.utc), sched=sched, lines=str(tmp_path / "l.sqlite"),
                 stats=str(tmp_path / "s.sqlite"), get=get, official={})
    assert pl["sport"] == "nfl" and pl["week"] == 8 and pl["dates"] == ["2026-11-01"] and pl["season"] == "2026-27"
    p = next(x for x in pl["props"] if x["market"] == "rec_yds")
    assert p["team"] == "GB" and p["opp"] == "CHI" and p["home"] and p["main"] == 64.5
    assert p["summary"]["season"]["n"] == 3 and p["summary"]["l5"]["n"] == 4
    assert p["ctx"]["group"] == "WR" and p["ctx"]["pos"] == "WR"
    td = next(x for x in pl["props"] if x["market"] == "anytime_td")
    assert td["main"] == 0.5                                                   # a yes-only market's line
    assert pl["games"][0]["lines"]["spread_home"] == -6.5 and pl["games"][0]["spots"]["GB"]["short"] and pl["games"][0]["spots"]["CHI"]["bye"]
    ab = pl["absences"]["2026-11-01|GB"]
    assert [a["pid"] for a in ab] == [300]                                     # the back, not the linebacker
    assert ab[0]["played"] == ["2025_09_GB_CHI", "2026_01_GB_CHI", "2026_02_DET_GB"]
    assert pl["depth"]["GB"]["WR"] == [[100, "Wes Wideout"]] and pl["heads"]["100"] == "1001"
    assert pl["players"]["100"]["logs"][0][COLS.index("rec_yds")] == 60
    assert "2026_01_GB_CHI" in pl["_boxes"](None) and pl["_box_dates"]["2026_01_GB_CHI"] == "2026-09-13"
    docs, old = tmp_path / "docs", tmp_path / "docs" / "nflbox" / "2025_09_GB_CHI.json"
    old.parent.mkdir(parents=True)
    old.write_text("kept")                                                  # a past game's box is never rewritten
    R.write(docs, dict(pl), today=dt.date(2026, 10, 29))
    assert (docs / "nfl_props.json").exists() and json.loads((docs / "nflbox" / "2026_01_GB_CHI.json").read_text())["teams"][1]["tri"] == "GB"
    assert old.read_text() == "kept"
    body = json.loads((docs / "nfl_props.json").read_text())
    assert "_boxes" not in body and "_box_dates" not in body


# ── the page ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_page_has_the_switch_and_both_market_tables():
    html = UI.page()
    assert 'id="lgb"' not in UI.PAGE and "sportBtn()" in html and "nfl_props.json" in html and "nba_props.json" in html
    # the page's NFL markets are the builder's, with the same parts
    m = re.search(r"MARKET_PARTS: \{(.*?)\},\n", UI.JS_APP, re.S)
    js = {k: v.replace('"', "").replace(" ", "").split(",") for k, v in re.findall(r"(\w+): \[([^\]]*)\]", m.group(1))}
    assert js == {k: list(v[1]) for k, v in R.MARKETS.items()}
    order = re.search(r"const NFL_ORDER = \[(.*?)\];", UI.JS_APP, re.S).group(1)
    assert sorted(re.findall(r'"(\w+)"', order)) == sorted(R.MARKETS)


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_rest_filters_short_week_and_bye():
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "core.js").write_text(UI.JS_CORE)
    (d / "t.js").write_text("""const C = require('./core.js');
const L = [{rest: 4}, {rest: 6}, {rest: 13}, {rest: null}, {rest: 0}];
console.log(JSON.stringify([C.filterLogs(L, {rest: 'short'}).map(l => l.rest), C.filterLogs(L, {rest: 'bye'}).map(l => l.rest)]));""")
    out = json.loads(subprocess.run([NODE, str(d / "t.js")], capture_output=True, text=True, check=True, cwd=d).stdout)
    assert out == [[4, 0], [13]]


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_page_scripts_parse():
    html = UI.page()
    d = pathlib.Path(tempfile.mkdtemp())
    for i, js in enumerate(re.findall(r"<script>(.*?)</script>", html, re.S)):
        (d / f"s{i}.js").write_text(js)
        r = subprocess.run([NODE, "--check", str(d / f"s{i}.js")], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


def test_every_nfl_filter_draws_its_boxes():
    # every NFL range filter (chip and sheet) has white boxes on the chart; percentages, lines and the margin on their
    # own scale, the signed ones labelled +/-
    cfg = UI.JS_APP[UI.JS_APP.index("const NFL_CFG = {"):]
    ranges = re.findall(r'\["(\w+)", "[^"]+", "[^"]+"\]', re.search(r"RANGES: \[(.*?\])\],", cfg, re.S).group(1))
    ovl = re.findall(r"(\w+): \"", re.search(r"OVL: \{(.*?)\},\n", cfg, re.S).group(1))
    chips = re.findall(r'"(\w+)"', re.search(r"const NFL_RCHIPS = \[(.*?)\];", UI.JS_APP).group(1))
    assert set(ranges) == set(ovl) and set(chips) <= set(ranges) and {"spr", "tot", "margin"} <= set(ranges)
    assert 'const OWN_OV = new Set(["snap_pct", "tgt_share", "spr", "tot", "margin"]), SIGNED_OV = new Set(["spr", "margin"]);' in UI.JS_APP
    assert "ym = own ? v => B - Math.abs(v) / (oMax / .86) * (B - T) : y;" in UI.JS_APP
    assert all(k in NS.LOG_COLS for k in ranges)                       # each is a column of every log row


# ── the Matchup page's football: nfl_stats.from_pbp extras, advanced(), nfl_research.adv_payload ─────────────────
ADV_COLS = PBP_COLS + ["play_id", "xpass", "pass", "pass_touchdown", "interception"]


def _aplay(**kw):
    base = {c: "" for c in ADV_COLS}
    base.update(season_type="REG", game_id="2026_01_GB_CHI", posteam="GB", defteam="CHI", wp=".5", qtr="1",
                two_point_attempt="0", aborted_play="0", sack="0", touchdown="0", qb_scramble="0", pass_touchdown="0",
                interception="0")
    base.update({k: str(v) for k, v in kw.items()})
    return [base[c] for c in ADV_COLS]


def test_pbp_extras_zones_big_plays_blitz_proe(monkeypatch):
    P, W, T, B = "00-0000001", "00-0000002", "00-0000004", "00-0000003"
    plays = [
        _aplay(play_id=1, play_type="pass", pass_attempt=1, qb_dropback=1, **{"pass": 1}, passer_player_id=P, receiver_player_id=W,
               complete_pass=1, yards_gained=31, air_yards=22, pass_location="left", xpass=.6, pass_touchdown=1),
        _aplay(play_id=2, play_type="pass", pass_attempt=1, qb_dropback=1, **{"pass": 1}, passer_player_id=P, receiver_player_id=T,
               complete_pass=0, yards_gained=0, air_yards=5, pass_location="middle", xpass=.5),
        _aplay(play_id=3, play_type="pass", pass_attempt=1, qb_dropback=1, **{"pass": 1}, passer_player_id=P, sack=1, yards_gained=-7, xpass=.7),
        _aplay(play_id=4, play_type="run", rush_attempt=1, rusher_player_id=B, yards_gained=10, run_location="middle", xpass=.3),
        _aplay(play_id=6, play_type="run", rush_attempt=1, rusher_player_id=B, yards_gained=9, run_location="middle"),       # one short
        _aplay(play_id=7, play_type="pass", pass_attempt=1, qb_dropback=1, **{"pass": 1}, passer_player_id=P, receiver_player_id=W,
               complete_pass=1, yards_gained=20, air_yards=12, pass_location="right"),
        _aplay(play_id=8, play_type="pass", pass_attempt=1, qb_dropback=1, **{"pass": 1}, passer_player_id=P, receiver_player_id=W,
               complete_pass=1, yards_gained=19, air_yards=12, pass_location="right"),
        _aplay(play_id=5, play_type="run", rush_attempt=1, rusher_player_id=B, yards_gained=3, run_location="left", run_gap="end", xpass=.4),
    ]
    ftn = {("2026_01_GB_CHI", "1"): (2, 6), ("2026_01_GB_CHI", "2"): (0, 6), ("2026_01_GB_CHI", "3"): (1, 6),
           ("2026_01_GB_CHI", "4"): (0, 8), ("2026_01_GB_CHI", "5"): (0, 7)}
    monkeypatch.setattr(NS, "pbp_rows", lambda s, c: ({k: i for i, k in enumerate(ADV_COLS)}, iter(plays)))
    *_, ex = NS.from_pbp(2026, 2026, posmap={2: "WR", 4: "TE", 3: "RB"}, ftn=ftn)
    assert ex["zone"]["CHI|all"] == {"dpl": [1, 1, 31, 1], "shm": [1, 0, 0, 0], "inr": [2, 2, 39, 0]}
    assert ex["zone"]["CHI|WR"] == {"dpl": [1, 1, 31, 1], "inr": [2, 2, 39, 0]} and ex["zone"]["CHI|TE"] == {"shm": [1, 0, 0, 0]}
    t = ex["tg"]["GB|2026_01_GB_CHI"]
    assert t["db"] == 5 and t["sacks"] == 1 and t["cdb"] == 3 and t["blitz"] == 2 and t["crun"] == 2 and t["box8"] == 1
    assert t["big_pass"] == 2 and t["long_pass"] == 31 and t["big_run"] == 1 and t["long_run"] == 10   # 20 and 10 count, 19 and 9 do not
    assert t["xn"] == 5 and t["pp"] == 3 and abs(t["xp"] - 2.5) < 1e-9          # 3 dropbacks vs 2.5 expected: +10%
    assert ex["qbb"]["1"] == {"b": [2, 1, 1, 31, 1, 0, 1], "n": [1, 1, 0, 0, 0, 0, 0]}   # blitzed: the TD and the sack
    assert ex["pexp"]["2"]["rec20"] == 2 and ex["pexp"]["3"]["rush10"] == 1
    # receivers against the blitz: charted targets only (plays 7 and 8 have no charting)
    assert ex["rbl"]["2"]["b"] == [1, 1, 31, 1] and ex["rbl"]["2"]["n"] == [0, 0, 0, 0] and ex["rbl"]["4"]["n"] == [1, 0, 0, 0]
    assert ex["tbl"]["GB"] == {"b": 1, "n": 1}


def test_passer_rating():
    assert NS.passer_rating(0, 0, 0, 0, 0) is None
    assert NS.passer_rating(10, 10, 300, 5, 0) == 158.3                       # the ceiling
    assert NS.passer_rating(30, 20, 230, 2, 1) == round((min(2.375, (20 / 30 - .3) * 5) + (230 / 30 - 3) * .25 + 2 / 30 * 20 + (2.375 - 25 / 30)) / 6 * 100, 1)


def test_advanced_team_sides_and_coverage(monkeypatch, tmp_path):
    games = {"g1": {"gid": "g1", "season": 2026, "home": "GB", "away": "CHI"}, "g2": {"gid": "g2", "season": 2026, "home": "DET", "away": "GB"}}
    extra = {"tg": {"GB|g1": {"db": 40, "sacks": 2, "cdb": 40, "blitz": 10, "crun": 20, "box8": 4, "big_pass": 3, "big_run": 2,
                              "long_pass": 50, "long_run": 20, "xn": 60, "xp": 33, "pp": 36},
                    "CHI|g1": {"db": 30, "sacks": 3, "cdb": 30, "blitz": 6, "crun": 25, "box8": 5, "big_pass": 1, "big_run": 4,
                               "long_pass": 25, "long_run": 40, "xn": 55, "xp": 30, "pp": 27}},
             "zone": {"CHI|WR": {"dpl": [2, 1, 30, 0]}}, "qbb": {}, "pexp": {"9": {"rec20": 1}}}
    monkeypatch.setattr(NS, "pfr_rows", lambda season, cur, kind: iter({
        "pass": [{"team": "GB", "opponent": "CHI", "times_pressured": "8", "pfr_player_id": "QBX"}],
        "def": [{"team": "CHI", "pfr_player_id": "CBX", "def_targets": "6", "def_completions_allowed": "4", "def_yards_allowed": "60",
                 "def_receiving_td_allowed": "1", "def_ints": "0", "def_adot": "10"}],
        "rush": [], "rec": []}[kind]))
    monkeypatch.setattr(NS, "ngs_season", lambda kind, season, cur: {})
    roster = {9: {"pfr": "CBX", "pos": "DB", "depth_pos": "CB", "team": "CHI"}, 1: {"pfr": "QBX", "pos": "QB", "team": "GB"}}
    logs9 = [(2026, 9, "DB") + tuple(_log(gid="g1", team="CHI", opp="GB", tackles=5))]    # his own line too: still a CB
    teams, players, zones = NS.advanced(2026, 2026, extra, games, logs9, roster)
    assert teams["GB"]["off"]["press_pct"] == 20.0 and teams["CHI"]["def"]["press_pct"] == 20.0     # 8 of GB's 40 dropbacks
    assert teams["CHI"]["def"]["big_pass_pg"] == 3.0 and teams["CHI"]["def"]["long_pass"] == 50       # what GB did to CHI
    assert teams["GB"]["off"]["proe"] == 5.0 and teams["CHI"]["def"]["proe"] == 5.0
    assert teams["GB"]["def"]["blitz_pct"] == 20.0 and teams["GB"]["def"]["box8_pct"] == 20.0          # CHI's offense faced
    c = players[9]
    assert c["pos"] == "CB" and c["team"] == "CHI" and c["cov"]["tgt"] == 6 and c["cov"]["rat"] == NS.passer_rating(6, 4, 60, 1, 0)
    assert zones[("CHI", "WR")] == {"g": 1, "cells": {"dpl": [2, 1, 30, 0]}}


def test_adv_payload_ranks_zones_and_cover(tmp_path):
    db = tmp_path / "s.sqlite"
    con = sqlite3.connect(db)
    con.executescript(NS.DDL)
    side = lambda big, press: {"games": 5, "big_pass_pg": big, "big_run_pg": 1.0, "press_pct": press, "sack_pct": 5.0, "blitz_pct": 30.0,
                               "box8_pct": 8.0, "ybc": 2.0, "proe": 0.0, "long_pass": 40, "long_run": 20, "db_pg": 40}
    for t, big, press in (("GB", 1.0, 30.0), ("CHI", 3.0, 20.0), ("DET", 2.0, 25.0)):
        con.execute("INSERT INTO team_adv VALUES (2026, ?, ?)", (t, json.dumps({"off": side(big, press), "def": side(big, press)})))
    con.execute("INSERT INTO team_adv VALUES (2026, 'MIN', ?)", (json.dumps({"off": dict(side(9, 9), games=1), "def": dict(side(9, 9), games=1)}),))
    con.execute("INSERT INTO team_adv VALUES (2025, 'MIN', ?)", (json.dumps({"off": side(0.5, 40.0), "def": side(0.5, 40.0)}),))
    con.execute("INSERT INTO def_zone VALUES (2026, 'CHI', 'WR', ?)", (json.dumps({"g": 2, "cells": {"dpl": [4, 2, 60, 0]}}),))
    con.execute("INSERT INTO def_zone VALUES (2026, 'GB', 'WR', ?)", (json.dumps({"g": 2, "cells": {"dpl": [0, 0, 0, 0]}}),))
    con.execute("INSERT INTO player_adv VALUES (2026, 9, 'CHI', 'CB', ?)", (json.dumps({"g": 5, "cov": {"tgt": 20, "cmp": 12, "yds": 150, "td": 1, "int": 1, "rat": 80.0, "adot": 9.0, "g": 5}}),))
    con.execute("INSERT INTO player_adv VALUES (2026, 7, 'GB', 'WR', ?)", (json.dumps({"g": 5, "rec20": 3}),))
    con.commit()
    out = R.adv_payload(con, 2026, ["GB", "CHI", "MIN"], {7}, {9: "Cee Bee"}, {9: {"status": "Questionable"}})
    assert out["n"] == 4 and out["teams"]["MIN"]["season"] == "2025-26"         # 1 game: last season stands in
    assert out["teams"]["MIN"]["ranks"]["def"]["big_pass_pg"] == 1 and out["teams"]["CHI"]["ranks"]["def"]["big_pass_pg"] == 4
    assert out["teams"]["GB"]["ranks"]["def"]["press_pct"] == 2                  # 1st = the most pressure (MIN 40%)
    assert out["zones"]["CHI"]["WR"]["cells"]["dpl"] == [2.0, 1.0, 30.0, 0.0] and out["zones"]["lg"]["WR"]["dpl"] == [1.0, 0.5, 15.0, 0.0]
    assert out["cover"]["CHI"] == [[9, "Cee Bee", "CB", 20, 12, 150, 1, 1, 80.0, 9.0, 5, "Questionable"]]
    assert out["players"]["7"]["rec20"] == 3 and "9" not in out["players"]



def test_coverage_splits_man_zone_and_routes(monkeypatch, tmp_path):
    # who was on the field each dropback (nflverse participation) joined to the play by play: routes, targets, catches,
    # yards and TDs against man and against zone, the route rate over his games, each defense's man / zone counts
    W, T, Q = "00-0000002", "00-0000004", "00-0000001"
    plays = [_aplay(play_id=pid, game_id="2026_01_GB_CHI", play_type="pass", pass_attempt=1, qb_dropback=1, passer_player_id=Q,
                    receiver_player_id=rc, complete_pass=cp, yards_gained=y, pass_touchdown=td)
             for pid, rc, cp, y, td in ((1, W, 1, 25, 1), (2, T, 1, 8, 0), (3, W, 0, 0, 0), (4, "", 0, 0, 0))]
    plays.append(_aplay(play_id=5, game_id="2026_01_GB_CHI", play_type="run", rush_attempt=1, rusher_player_id="00-0000003"))
    part = [{"nflverse_game_id": "2026_01_GB_CHI", "play_id": str(i), "defense_man_zone_type": cov, "offense_players": on}
            for i, cov, on in ((1, "MAN_COVERAGE", f"{W};{T};{Q}"), (2, "ZONE_COVERAGE", f"{W};{T};{Q}"), (3, "MAN_COVERAGE", f"{W};{Q}"),
                               (4, "", f"{W};{T};{Q}"), (5, "ZONE_COVERAGE", f"{W};{T};{Q}"))]
    f = tmp_path / "part.csv"
    f.write_text("x")
    monkeypatch.setattr(NS, "pbp_rows", lambda s, c: ({k: i for i, k in enumerate(ADV_COLS)}, iter(plays)))
    monkeypatch.setattr(NS.C, "cached", lambda path, max_age=0: f)
    monkeypatch.setattr(NS.C, "iter_rows", lambda path, max_age=0: iter(part))
    monkeypatch.setattr(NS.C, "CACHE", tmp_path)
    monkeypatch.setattr(NS, "COV_MIN_ROUTES", 1)
    players, teams = NS.coverage_splits(2026, 2026, {2: {"pos": "WR"}, 4: {"pos": "TE"}, 1: {"pos": "QB"}})
    assert players[2] == {"man": [2, 2, 1, 25, 1], "zone": [1, 0, 0, 0, 0], "rt": [4, 4]}     # the run (play 5) is no route
    assert players[4] == {"man": [1, 0, 0, 0, 0], "zone": [1, 1, 1, 8, 0], "rt": [3, 4]}
    assert 1 not in players and teams == {"CHI": {"man": 2, "zone": 1}}
    # cached by the file's mtime: a second call reads the cache, not the files
    monkeypatch.setattr(NS, "pbp_rows", lambda s, c: (_ for _ in ()).throw(AssertionError("parsed again")))
    assert NS.coverage_splits(2026, 2026, {})[0][2]["man"] == [2, 2, 1, 25, 1]
    # no file published (this season, until it ends): nothing
    monkeypatch.setattr(NS.C, "cached", lambda path, max_age=0: (_ for _ in ()).throw(OSError("404")))
    assert NS.coverage_splits(2027, 2027, {}) == ({}, {})


def test_adv_payload_man_zone_from_last_season(tmp_path):
    db = tmp_path / "s.sqlite"
    con = sqlite3.connect(db)
    con.executescript(NS.DDL)
    side = {"games": 5, "big_pass_pg": 2.0, "big_run_pg": 1.0, "press_pct": 20.0, "sack_pct": 5.0, "blitz_pct": 30.0, "box8_pct": 8.0,
            "ybc": 2.0, "proe": 0.0, "long_pass": 40, "long_run": 20, "db_pg": 40}
    for s_, t, man in ((2026, "CHI", None), (2026, "GB", None), (2025, "CHI", 20.0), (2025, "GB", 40.0)):
        d = dict(side, **({"man_pct": man} if man is not None else {}))
        con.execute("INSERT INTO team_adv VALUES (?, ?, ?)", (s_, t, json.dumps({"off": side, "def": d})))
    v = {"man": [100, 20, 14, 200, 2], "zone": [200, 30, 20, 220, 1], "rt": [300, 320]}
    con.execute("INSERT INTO player_adv VALUES (2025, 7, 'GB', 'WR', ?)", (json.dumps({"g": 17, "vcov": v}),))
    con.execute("INSERT INTO player_adv VALUES (2026, 7, 'GB', 'WR', ?)", (json.dumps({"g": 5, "rec20": 2}),))
    con.commit()
    out = R.adv_payload(con, 2026, ["GB", "CHI"], {7}, {}, {})
    assert out["players"]["7"]["vcov"] == v and out["players"]["7"]["vcov_season"] == "2025-26" and out["players"]["7"]["rec20"] == 2
    assert out["man"] == {"season": "2025-26", "lg": 30.0, "teams": {"CHI": 20.0, "GB": 40.0}}
    # once a season's own file is out its splits win; a player with no prop on the slate is left out
    v26 = {"man": [50, 9, 6, 80, 1], "zone": [90, 12, 9, 100, 0], "rt": [140, 150]}
    con.execute("UPDATE player_adv SET js=? WHERE season=2026 AND pid=7", (json.dumps({"g": 5, "vcov": v26}),))
    con.execute("INSERT INTO player_adv VALUES (2025, 8, 'GB', 'TE', ?)", (json.dumps({"g": 17, "vcov": v}),))
    con.commit()
    out = R.adv_payload(con, 2026, ["GB", "CHI"], {7}, {}, {})
    assert out["players"]["7"]["vcov"] == v26 and out["players"]["7"]["vcov_season"] == "2026-27" and "8" not in out["players"]


def test_page_has_no_duplicate_function_names():
    # a second `function x` in the page's script silently replaces the first: the NFL Matchup page's zoneCard once
    # replaced the NBA's (the assists and rebounds zone cards went blank). Every name once, and no const/let clashes
    for js in (UI.JS_APP, UI.JS_CORE):
        fns = re.findall(r"^\s*(?:async\s+)?function\s+(\w+)\s*\(", js, re.M)
        assert len(fns) == len(set(fns)), sorted({f for f in fns if fns.count(f) > 1})
        top = re.findall(r"^(?:const|let|var)\s+(\w+)\s*=", js, re.M)
        assert not set(top) & set(fns) and len(top) == len(set(top))


def test_field_payload_per_game_league_and_ranks(tmp_path):
    db = tmp_path / "s.sqlite"
    con = sqlite3.connect(db)
    con.executescript(NS.DDL)
    for t, g, yds in (("CHI", 2, 60), ("GB", 4, 40), ("DET", 2, 20)):
        con.execute("INSERT INTO def_zone VALUES (2026, ?, 'all', ?)", (t, json.dumps({"g": g, "cells": {"dpl": [4, 2, yds, 0]}})))
        con.execute("INSERT INTO def_zone VALUES (2026, ?, 'WR', ?)", (t, json.dumps({"g": g, "cells": {"dpl": [2, 1, yds / 2, 0]}})))
    for t, att, yds in (("CHI", 10, 60), ("GB", 10, 30), ("DET", 4, 40)):         # DET: too few carries to rank
        con.execute("INSERT INTO rush_dir VALUES (2026, 'd', ?, ?)", (t, json.dumps({"le": [att, yds, 0]})))
    con.execute("INSERT INTO rush_dir VALUES (2026, 'p', '7', ?)", (json.dumps({"le": [5, 25, 1]}),))
    con.execute("INSERT INTO tgt_tree VALUES (2026, 7, ?)", (json.dumps({"dpl": [3, 2, 50]}),))
    con.execute("INSERT INTO pass_tree VALUES (2026, 9, ?)", (json.dumps({"dpl": [6, 3, 90, 1, 0]}),))
    con.commit()
    logs = {7: [_log(date="2026-09-14"), _log(date="2026-09-21")], 9: [_log(date="2026-09-14")]}
    f = R.field_payload(con, 2026, ["CHI", "GB"], {7, 9}, logs)
    s = f["2026-27"]
    assert f["seasons"] == ["2026-27", "2025-26"] and "2025-26" not in f                 # no rows last season: no block
    assert s["def"]["CHI"]["g"] == 2 and s["def"]["CHI"]["pass"]["all"]["dpl"] == [2.0, 1.0, 30.0, 0.0]
    assert s["lg"]["pass"]["all"]["dpl"] == [1.5, 0.75, 15.0, 0.0]                     # 120 yds over 8 team-games
    assert s["rank"]["pass"]["all"]["dpl"] == {"CHI": 3, "GB": 1}                        # DET 10 a game, GB 10 (a tie shares 1st), CHI 30
    assert s["def"]["GB"]["rush"] == {"le": [10, 30, 0]} and s["rank"]["rush"]["le"] == {"CHI": 2, "GB": 1}
    assert s["lg"]["rush"]["le"] == [8.0, 43.3, 0.0]
    assert s["p"]["7"] == {"recv": {"dpl": [3, 2, 50]}, "rush": {"le": [5, 25, 1]}, "g": 2} and s["p"]["9"]["pass"]["dpl"][2] == 90
