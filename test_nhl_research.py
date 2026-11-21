"""nhl_research: the NHL payload the page reads (nhl_props.json) — live state and power-play points from the scoring
summary, ESPN's injuries and starting goalies by name within the team, defense vs position, roles (last 3 games against
the season; a goalie's starts), who gains ice time without a player, the slate's roll, the moneyline, box scores; and the
whole build over small stores. MUTANTS in test_mutants()."""
import datetime as dt
import importlib.util
import json
import pathlib
import sqlite3
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nfl_lines as NL
import nhl_common as C
import nhl_onoff as O
import nhl_research as R
import nhl_stats as S
import test_nhl_lines as TL
import test_nhl_onoff as TO

NOW = TL.NOW                                             # 2026-11-01 18:00 UTC: EDM @ NYR tonight, OTT @ ANA late
C.CACHE = pathlib.Path(tempfile.mkdtemp())               # the tests' fetches never touch nhl_cache/


def fake_get(extra=None):
    """The NHL's scores, box scores and ESPN, by URL."""
    docs = {
        "score/2026-11-01": {"games": [
            {"id": 2026020230, "gameState": "LIVE", "period": 2, "clock": {"secondsRemaining": 600, "timeRemaining": "10:00"},
             "periodDescriptor": {"periodType": "REG"}, "awayTeam": {"score": 2, "sog": 20}, "homeTeam": {"score": 1, "sog": 15},
             "goals": [{"strength": "pp", "playerId": 8478402, "assists": [{"playerId": 8477934}]},
                       {"strength": "ev", "playerId": 8477934, "assists": [{"playerId": 8478402}]},
                       {"strength": "PP", "playerId": 8476468, "assists": []}]}]},
        "score/2026-11-02": {"games": [{"id": 2026020231, "gameState": "FUT", "period": 0}]},
        "gamecenter/2026020230/boxscore": {"awayTeam": {"abbrev": "EDM"}, "homeTeam": {"abbrev": "NYR"}, "playerByGameStats": {
            "awayTeam": {"forwards": [{"playerId": 8478402, "goals": 1, "assists": 1, "points": 2, "sog": 4, "blockedShots": 0,
                                       "hits": 1, "plusMinus": 1, "pim": 0, "toi": "14:30", "position": "C", "name": {"default": "C. McDavid"}}],
                         "defense": [], "goalies": [{"playerId": 8476999, "saves": 14, "shotsAgainst": 15, "toi": "30:00",
                                                     "position": "G", "name": {"default": "M. Tomkins"}}]},
            "homeTeam": {"forwards": [], "defense": [], "goalies": []}}},
        "injuries": {"injuries": [{"displayName": "Edmonton Oilers", "injuries": [
            {"athlete": {"displayName": "Leon Draisaitl"}, "status": "Day-To-Day", "date": "2026-11-01T15:00Z",
             "details": {"type": "Upper Body", "side": "Not Specified"}, "shortComment": "Draisaitl is day-to-day."},
            {"athlete": {"displayName": "Zach Hyman"}, "status": "Injured Reserve", "date": "2026-10-20T15:00Z",
             "details": {"type": "Wrist"}},
            {"athlete": {"displayName": "Nobody Here"}, "status": "Out"}]},
            {"displayName": "New York Rangers", "injuries": [{"athlete": {"displayName": "J.T. Miller"}, "status": "Probable"}]}]},
        "scoreboard?dates=20261101": {"events": [{"competitions": [{"competitors": [
            {"homeAway": "away", "team": {"abbreviation": "EDM"}, "probables": [
                {"name": "probableStartingGoalie", "athlete": {"displayName": "Matt Tomkins"}, "status": {"name": "Confirmed"}}]},
            {"homeAway": "home", "team": {"abbreviation": "NYR"}, "probables": []}]}]}]},
        "scoreboard?dates=20261102": {"events": []},
    }
    docs.update(extra or {})

    def get(url):
        for k, v in docs.items():
            if url.endswith(k):
                return v
        raise IOError(url)
    return get


# ── live ────────────────────────────────────────────────────────────────────────────────────────────────────────
def check_live(M):
    games = [g for g in TL.sched() if g["state"] != "final"] + [dict(TL.sched()[2], date="2026-11-01")]
    lv = M.live_state(games, fake_get())
    a, b, c = lv["2026020230"], lv["2026020231"], lv["2026020100"]
    return (a["state"] == "live" and a["label"] == "2nd 10:00" and a["frac"] == .5 and a["score"] == [2, 1]
            and a["ppp"] == {"8478402": 1, "8477934": 1, "8476468": 1} and b["state"] == "pregame"
            and c["state"] == "final" and c["score"] == [3, 2])


def test_live():
    """Power-play points: the scorer and the assists of a goal at "pp" (either case); an even-strength goal none. A game
    the feed leaves out is final once the schedule has its score."""
    C.CACHE = pathlib.Path(tempfile.mkdtemp())
    assert check_live(R)
    lv = R.live_state([g for g in TL.sched() if g["gid"] == "2026020230"], fake_get())
    bx = R.live_boxes(lv, fake_get())["2026020230"]
    assert bx[8478402]["ppp"] == 1 and bx[8478402]["min"] == 14.5 and bx[8476999]["saves"] == 14 and bx[8478402]["_team"] == "EDM"
    games = [g for g in TL.sched() if g["gid"] == "2026020230"]
    b = R.live_box_files({"2026020230": bx}, lv, games, {})["2026020230"]
    assert b["live"] and b["teams"][0]["tri"] == "EDM" and b["teams"][0]["pts"] == 2
    assert [x[0] for x in b["teams"][0]["players"]] == [8478402, 8476999], "skaters, then goalies"


# ── ESPN ────────────────────────────────────────────────────────────────────────────────────────────────────────
PLAYERS = {8478402: {"name": "Connor McDavid", "team": "EDM", "pos": "C"}, 8477934: {"name": "Leon Draisaitl", "team": "EDM", "pos": "C"},
           8475786: {"name": "Zach Hyman", "team": "EDM", "pos": "L"}, 8476999: {"name": "Matt Tomkins", "team": "EDM", "pos": "G"},
           8476468: {"name": "J.T. Miller", "team": "NYR", "pos": "C"}, 8480000: {"name": "Nobody Here", "team": "NYR", "pos": "C"}}


def check_inj(M):
    inj = M.injuries(PLAYERS, fake_get())
    return (inj[8477934]["status"] == "Day-To-Day" and not inj[8477934]["long"] and inj[8477934]["reason"] == "Upper Body"
            and inj[8475786]["status"] == "Out" and inj[8475786]["long"] and 8480000 not in inj
            and inj[8476468]["status"] is None)


def test_injuries_and_goalies():
    """By name within the team ESPN files him under (an Oiler's name does not match a Ranger); injured reserve is Out,
    long; a status the page has no use for (Probable) is kept with no status."""
    C.CACHE = pathlib.Path(tempfile.mkdtemp())
    assert check_inj(R)
    games = [g for g in TL.sched() if g["state"] != "final"]
    gl = R.goalies(games, PLAYERS, fake_get())
    assert gl == {"2026020230": {"EDM": {"pid": 8476999, "name": "Matt Tomkins", "status": "Confirmed"}}}


# ── logs: a small league ────────────────────────────────────────────────────────────────────────────────────────
COL = R.COL


def row(date, gid, team, opp, home, **kw):
    r = [None] * len(R.LOG_COLS)
    base = dict(date=date, gid=gid, team=team, opp=opp, home=home, min=15.0, goals=0, assists=0, points=0, shots=2,
                blocks=0, saves=None, ppp=0, rest=1, pp_min=1.0, sh_min=0.0, ev_min=14.0, shifts=20, attempts=4,
                shot_share=10.0, pp_share=30.0, margin=1)
    for k, v in {**base, **kw}.items():
        r[COL[k]] = v
    return r


def league():
    """EDM's 12 games of 2026-27 (10-08 .. 10-30) against NYR and BOS. 97 (C) plays them all, his ice time up from 15 to
    21 over the last 3; 29 (C) misses the last 3; 18 (L) is a winger whose time rises when 29 is out; 44 (D) too, but a
    defenseman does not replace a center. Goalie 90 started the first 9, 91 the last 3. Opponents' centers score."""
    logs, pos = {}, {97: "C", 29: "C", 18: "L", 44: "D", 90: "G", 91: "G", 300: "C", 301: "D"}
    days = [f"2026-10-{d:02d}" for d in range(8, 32, 2)]
    for i, d in enumerate(days):
        gid, opp = f"20260200{i:02d}", ("NYR" if i % 2 else "BOS")
        late = i >= 9
        logs.setdefault(97, []).append(row(d, gid, "EDM", opp, i % 2, min=21.0 if late else 15.0, shots=4 if late else 2))
        if not late:
            logs.setdefault(29, []).append(row(d, gid, "EDM", opp, i % 2, min=19.0))
        logs.setdefault(18, []).append(row(d, gid, "EDM", opp, i % 2, min=18.0 if late else 14.0, pp_min=3.0 if late else 1.0))
        logs.setdefault(44, []).append(row(d, gid, "EDM", opp, i % 2, min=24.0 if late else 20.0))
        g = 91 if late else 90
        logs.setdefault(g, []).append(row(d, gid, "EDM", opp, i % 2, min=60.0, saves=25, starter=1, shots=None))
        logs.setdefault(300, []).append(row(d, gid, opp, "EDM", 1 - i % 2, goals=1 if opp == "NYR" else 0, points=1, shots=3))
        logs.setdefault(301, []).append(row(d, gid, opp, "EDM", 1 - i % 2, goals=0, points=0, shots=1))
    return logs, pos, days


def check_dvp(M):
    logs, pos, days = league()
    t = M.dvp_tables(logs, pos, 2026)
    v, r = t["val"]["C"]["goals"], t["dvp"]["C"]["goals"]
    return v["EDM"] == .5 and r["EDM"] == 3 and v["NYR"] == 0 and r["NYR"] == r["BOS"] == 1 and t["n"]["EDM"] == 12


def test_dvp():
    """Against EDM, the opponents' centers scored in 6 of 12 games: half a goal a game, ranked behind NYR's and BOS's
    none (1st = allows the least; a tie shares the rank)."""
    assert check_dvp(R)


def check_roles(M):
    logs, pos, days = league()
    players = {p: {"team": "EDM", "name": f"P{p}"} for p in (97, 29, 18, 44, 90, 91)}
    j = M.roles(logs, pos, players, {"EDM"}, 2026)
    rows = {r["pid"]: r for r in j["rows"]}
    a, g = rows.get(97), rows.get(91)
    return (j["mode"] == "recent" and a is not None and a["st"]["min"] == [21.0, 16.5] and "P29" in a["out"]
            and a["starts"] == [0, 0, 0, 3] and g is not None and g["starts"] == [3, 0, 9, 3] and g["st"]["min"] == [60.0, 0.0]
            and 90 in rows and 29 not in rows)


def test_roles():
    """Last 3 games against the season (the last 3 in it): 97's ice time 15 -> 21 a game is 21 against 16.5, 29 (a
    regular who sat them) is the why; 91 now starts (3 of 3 against 0 of 9), 90 lost his start; 29, not playing, is no
    role change."""
    assert check_roles(R)


def check_gains(M):
    logs, pos, days = league()
    gl = [(r[COL["date"]], r[COL["gid"]]) for r in logs[97]]
    played = {r[COL["gid"]] for r in logs[29]}
    out = {e["pid"]: e for e in M.gains(logs, pos, "EDM", played, gl, 29)}
    return 97 in out and 18 in out and out[18]["pp"] == 2.0 and 44 not in out and out[97]["n"] == 3


def test_gains():
    """Without 29 (a center) the forwards who gained 1.5+ minutes a game are named, with their power-play gain; the
    defenseman who gained as much is not (forwards replace forwards)."""
    assert check_gains(R)


def check_slate(M):
    sched = TL.sched()
    late = dt.datetime(2026, 11, 2, 9, 0, tzinfo=dt.timezone.utc)     # 4 AM ET: still Nov 1's slate (rolls at 6)
    d1, _, _ = M.slate(sched, late, lambda c: {g["gid"]: {"state": "pregame"} for g in c})
    d2, _, _ = M.slate(sched, NOW, lambda c: {g["gid"]: {"state": "final" if g["date"] == "2026-11-01" else "pregame"} for g in c})
    two = sched + [dict(sched[0], gid="2026020229", away="UTA", home="PHI")]      # one of today's two still to play
    d3, _, _ = M.slate(two, NOW, lambda c: {g["gid"]: {"state": "final" if g["gid"] == "2026020230" else "pregame"} for g in c})
    return d1 == ["2026-11-01", "2026-11-02"] and d2 == ["2026-11-02", "2026-11-03"] and d3 == ["2026-11-01", "2026-11-02"]


def test_slate():
    """Today and tomorrow (US Eastern, rolled at 6 AM); today drops once all of its games are final."""
    assert check_slate(R)


def test_moneyline_and_boxes():
    db = pathlib.Path(tempfile.mkdtemp()) / "l.sqlite"
    con = sqlite3.connect(db)
    con.executescript(NL.DDL)
    con.executemany("INSERT INTO game_lines VALUES (?,?,?,?,?,?,?,?)",
                    [("2026-11-01T17:00:00", "fd", "g1", "", "moneyline", "home", None, 2.5),
                     ("2026-11-01T18:00:00", "fd", "g1", "", "moneyline", "home", None, 2.0),
                     ("2026-11-01T18:00:00", "fd", "g1", "", "moneyline", "away", None, 1.8333)])
    con.commit()
    ml = R.moneyline(con, ["g1", "g2"])
    assert set(ml) == {"g1"} and ml["g1"]["home_odds"] == 2.0 and ml["g1"]["home"] == .478, "the latest prices, no vig"
    logs, pos, days = league()
    sched = [{"gid": r[COL["gid"]], "date": r[COL["date"]], "away": "EDM" if r[COL["home"]] == 0 else r[COL["opp"]],
              "home": r[COL["opp"]] if r[COL["home"]] == 0 else "EDM", "away_score": 3, "home_score": 2} for r in logs[97]]
    b = R.box_files(logs, pos, {97: "Ninety Seven"}, sched, {"2026020011"})
    assert list(b) == ["2026020011"]
    edm = next(t for t in b["2026020011"]["teams"] if t["tri"] == "EDM")
    assert [x[0] for x in edm["players"]] == [97, 18, 44, 91] and edm["players"][0][1] == "Ninety Seven"


# ── the whole build over small stores ──────────────────────────────────────────────────────────────────────────
def stores():
    d = pathlib.Path(tempfile.mkdtemp())
    lines = d / "nhl_lines.sqlite"
    E = "Edmonton Oilers @ New York Rangers"
    TL.run_cycle(lines, [(E, "Connor McDavid", "shots", 3.5, "over", 1.71), (E, "Connor McDavid", "shots", 3.5, "under", 2.1),
                         (E, "J.T. Miller", "points", 0.5, "over", 1.8), (E, "J.T. Miller", "points", 0.5, "under", 2.0)])
    stats = d / "nhl_stats.sqlite"
    con = sqlite3.connect(stats)
    con.executescript(S.DDL)
    days = [f"2026-10-{x:02d}" for x in range(8, 32, 2)]
    for i, day in enumerate(days):
        gid = f"20260200{i:02d}"
        for pid, team, opp, home, p_ in ((8478402, "EDM", "BOS", 0, "C"), (8476468, "NYR", "BOS", 1, "C"), (8476999, "EDM", "BOS", 0, "G")):
            r = row(day, gid + team, team, opp, home, shots=3 + i % 3 if p_ != "G" else None, saves=25 if p_ == "G" else None,
                    starter=1 if p_ == "G" else None, sa=27 if p_ == "G" else None, min=60.0 if p_ == "G" else 15.0)
            con.execute(f"INSERT INTO logs VALUES (?,?,?,{','.join('?' * len(R.LOG_COLS))})", (2026, pid, p_, *r))
        for team in ("EDM", "NYR", "BOS"):
            con.execute("INSERT INTO team_games VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (2026, gid + team, day, team, "BOS", 0, 3, 2, 30, 28, 3, 1, 240, 20, 14, 55, 8))
    for pid, (nm, t, p_) in {8478402: ("Connor McDavid", "EDM", "C"), 8477934: ("Leon Draisaitl", "EDM", "C"),
                             8476999: ("Matt Tomkins", "EDM", "G"), 8476468: ("J.T. Miller", "NYR", "C")}.items():
        con.execute("INSERT INTO players VALUES (?,?,?,?,?,?,?)", (pid, nm, t, p_, C.headshot(2026, t, pid), None, None))
    con.execute("INSERT INTO meta VALUES ('meta', ?)", (json.dumps({"built_at": "2026-11-01T17:00:00+00:00"}),))
    con.commit()
    onoff = d / "nhl_onoff.sqlite"
    oc = O.connect(onoff)
    pbp, sh = TO.game()
    splits, L, _ = O.parse(pbp, sh)
    O.store(oc, "2026020011EDM", 2026, "2026-10-30", "json", splits, L)
    oc.commit()
    O.refresh_lines(oc)
    return d, lines, stats, onoff


def check_mates(M):
    """The With / Without sheet: the skaters by ice time, then the goalie (60 minutes a game would put him first)."""
    _, lines, stats, onoff = stores()
    pl = M.build(now=NOW, sched=TL.sched(), lines=lines, stats=stats, onoff=onoff, get=fake_get())
    return [m["pid"] for m in pl["mates"]["EDM"]["mates"]] == [8478402, 8476999]


def check_moved(M):
    """A player on another team since his last game (a trade, a call-up): the prop's team from the player search, his
    face filed under it."""
    _, lines, stats, onoff = stores()
    con = sqlite3.connect(stats)
    con.execute("UPDATE players SET team='SJS', headshot=? WHERE pid=8476468", (C.headshot(2026, "SJS", 8476468),))
    con.execute("UPDATE logs SET team='SJS' WHERE pid=8476468")
    con.commit()
    con.close()
    memo = C.CACHE / "search.json"
    memo.write_text(json.dumps({"j.t. miller": [0, [[8476468, "NYR"]]]}))
    try:
        pl = M.build(now=NOW, sched=TL.sched(), lines=lines, stats=stats, onoff=onoff, get=fake_get())
    finally:
        memo.unlink()
    p = next(x for x in pl["props"] if x["pid"] == 8476468)
    return p["team"] == "NYR" and pl["players"]["8476468"]["headshot"].endswith("/NYR/8476468.png")


def test_build():
    C.CACHE = pathlib.Path(tempfile.mkdtemp())
    d, lines, stats, onoff = stores()
    pl = R.build(now=NOW, sched=TL.sched(), lines=lines, stats=stats, onoff=onoff, get=fake_get())
    for k in ("sport", "generated_at", "season", "dates", "log_cols", "markets", "sources", "games", "props", "players", "injuries",
              "flags", "absences", "related", "inj_report", "mates", "lineups", "depth", "ranks", "proj_players", "proj_meta", "usage",
              "teams", "roles", "vs", "heads"):
        assert k in pl, k
    assert pl["sport"] == "nhl" and pl["season"] == "2026-27" and pl["dates"] == ["2026-11-01", "2026-11-02"]
    p = next(x for x in pl["props"] if x["pid"] == 8478402 and x["market"] == "shots")
    assert p["team"] == "EDM" and p["opp"] == "NYR" and p["main"] == 3.5 and p["summary"]["l10"]["n"] == 10
    assert p["ctx"]["group"] == "C" and p["live"]["value"] == 4 and p["live"]["frac"] == .5
    g = next(x for x in pl["games"] if x["gid"] == "2026020230")
    assert g["state"] == "live" and g["goalies"]["EDM"]["pid"] == 8476999 and "ppp" not in g
    assert pl["injuries"]["2026-11-01|8478402"]["official"] is None and pl["depth"]["EDM"]["G"] == [[190, ""]]
    ir = pl["inj_report"]["2026-11-01|EDM"]["players"]
    assert [e["pid"] for e in ir] == [8477934] or ir == [], "Draisaitl listed only once he has played for EDM"
    R.write(d / "docs", pl, today=dt.date(2026, 11, 1))
    j = json.loads((d / "docs" / "nhl_props.json").read_text())
    assert j["props"] and (d / "docs" / "nhlbox" / "2026020230.json").exists(), "the live game's box score"
    assert len(list((d / "docs" / "nhlbox").glob("*.json"))) == 1, "a logged game off the schedule gets none"
    assert check_mates(R) and check_moved(R)


def _mutant(name, old, new):
    src = pathlib.Path(R.__file__).read_text()
    assert src.count(old) == 1, (name, old)
    f = pathlib.Path(tempfile.mkdtemp()) / f"{name}.py"
    f.write_text(src.replace(old, new))
    spec = importlib.util.spec_from_file_location(name, f)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_mutants():
    C.CACHE = pathlib.Path(tempfile.mkdtemp())
    cases = [
        ("nhl_research_m1", 'if (gl.get("strength") or "").lower() == "pp":', 'if (gl.get("strength") or "").lower() != "sh":',
         check_live, "an even-strength goal is no power-play point"),
        ("nhl_research_m2", 'status = "Out" if longo else INJ_MAP.get(raw)', "status = INJ_MAP.get(raw)", check_inj, "injured reserve is Out"),
        ("nhl_research_m3", "pid = res.resolve(a.get(\"displayName\") or \"\", (team,)) if team else None",
         "pid = res.resolve(a.get(\"displayName\") or \"\", tuple(C.TEAMS)) if team else None", check_inj, "the name within his team"),
        ("nhl_research_m4", "dvp[grp][m] = _rank(avgs)", "dvp[grp][m] = _rank(avgs, low_first=False)", check_dvp, "1st allows the least"),
        ("nhl_research_m5", "if y == pid or yg not in (\"C\", \"W\", \"D\") or (grp in (\"C\", \"W\", \"D\") and (yg == \"D\") != (grp == \"D\")):",
         "if y == pid or yg not in (\"C\", \"W\", \"D\"):", check_gains, "forwards replace forwards"),
        ("nhl_research_m6", "k0 = 1 if first and all(", "k0 = 1 if first and any(", check_slate, "today drops once all are final"),
        ("nhl_research_m7", "now, before = starts(recent_g), starts(set(tg[:-ROLE_RECENT]))",
         "now, before = starts(set(tg[:-ROLE_RECENT])), starts(recent_g)", check_roles, "a goalie's starts now and before"),
        ("nhl_research_m8", "            recent, base = cur[-ROLE_RECENT:], cur", "            recent, base = cur[-ROLE_RECENT:], cur[:-ROLE_RECENT]",
         check_roles, "the season average has the last 3 in it"),
        ("nhl_research_m9", 'mates[t] = {"gids": gl, "mates": sk[:27] + gk[:3]}',
         'mates[t] = {"gids": gl, "mates": sorted(sk + gk, key=lambda m: -m["mpg"])[:30]}', check_mates, "goalies after the skaters"),
        ("nhl_research_m10", 'elif team and players[pid].get("team") != team:', "elif False:", check_moved, "a moved player's face"),
    ]
    for name, old, new, check, label in cases:
        assert not check(_mutant(name, old, new)), f"mutant survived: {label}"
