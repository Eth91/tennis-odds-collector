"""nhl_onoff: the stretches between line changes, whose an event is (the stretch ending at its time, an assist made before a
change), power-play points from the situation code, the pair splits the WOWY tab reads, the lines, the HTML report's
shifts, the season file and the lines table. MUTANTS in test_mutants()."""
import importlib.util
import json
import pathlib
import sqlite3
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nhl_onoff as O

HOME, AWAY = 22, 3                                       # EDM at home, NYR away
SKA = {"EDM": [101, 102, 103, 104, 105, 106, 111, 112], "NYR": [201, 202, 203, 204, 205, 206, 211, 212]}
POS = {101: "C", 102: "L", 103: "R", 104: "C", 105: "L", 106: "R", 111: "D", 112: "D", 190: "G",
       201: "C", 202: "L", 203: "R", 204: "C", 205: "L", 206: "R", 211: "D", 212: "D", 290: "G"}


def spot(pid):
    team = HOME if pid < 200 else AWAY
    return {"teamId": team, "playerId": pid, "sweaterNumber": pid % 100, "positionCode": POS[pid],
            "firstName": {"default": "P"}, "lastName": {"default": str(pid)}}


def ev(kind, t, details, code="1551", period=1):
    m, s = divmod(t - (period - 1) * 1200, 60)
    return {"typeDescKey": kind, "periodDescriptor": {"number": period, "periodType": "REG"}, "timeInPeriod": f"{m:02d}:{s:02d}",
            "situationCode": code, "details": details, "eventId": t}


def game():
    """Two forward lines a side swapping at 100 s, two defensemen and the goalie throughout (0-200 s). EDM's 101 scores
    at 100 (the change) from 111: the stretch ending at 100 is his. A power-play goal at 150 (NYR's 212 off 120-180).
    105 changes at 180 and assists on the goal at 190."""
    sh = []
    for t in ("EDM", "NYR"):
        a, b = SKA[t][:3], SKA[t][3:6]
        sh += [(p, 0, 100) for p in a] + [(p, 100, 200) for p in b] + [(SKA[t][6], 0, 200)]
    sh += [(112, 0, 200), (212, 0, 120), (212, 180, 200), (190, 0, 200), (290, 0, 200)]
    sh = [x for x in sh if x[0] != 105] + [(105, 100, 180)]      # 105 changes early: off at 180
    pbp = {"homeTeam": {"id": HOME, "abbrev": "EDM"}, "awayTeam": {"id": AWAY, "abbrev": "NYR"},
           "rosterSpots": [spot(p) for p in POS],
           "plays": [ev("goal", 100, {"scoringPlayerId": 101, "assist1PlayerId": 111, "eventOwnerTeamId": HOME, "goalieInNetId": 290}),
                     ev("shot-on-goal", 50, {"shootingPlayerId": 201, "goalieInNetId": 190, "eventOwnerTeamId": AWAY}),
                     ev("goal", 150, {"scoringPlayerId": 104, "assist1PlayerId": 112, "eventOwnerTeamId": HOME, "goalieInNetId": 290},
                        code="1451"),
                     ev("blocked-shot", 60, {"shootingPlayerId": 202, "blockingPlayerId": 111, "reason": "blocked", "eventOwnerTeamId": AWAY}),
                     ev("blocked-shot", 70, {"shootingPlayerId": 203, "blockingPlayerId": 201, "reason": "teammate-blocked",
                                             "eventOwnerTeamId": AWAY}),
                     ev("goal", 190, {"scoringPlayerId": 106, "assist1PlayerId": 105, "eventOwnerTeamId": HOME, "goalieInNetId": 290}),
                     ev("hit", 30, {"hittingPlayerId": 211, "hitteePlayerId": 101, "eventOwnerTeamId": AWAY})]}
    return pbp, sh


def check_parse(M):
    pbp, sh = game()
    splits, lines, lost = M.parse(pbp, sh)
    E, N = splits["EDM"], splits["NYR"]
    ix = lambda k: M.S[k]
    ok = not lost
    ok &= E["toi"]["101"][0] == 100 and E["toi"]["111"][0] == 200 and E["toi"]["105"][0] == 80
    ok &= E["toi"]["101"][1][ix("goals")] == 1 and E["toi"]["111"][1][ix("assists")] == 1
    # the goal at the change is the old line's: 111's assist counts with 102 on the ice, not with 104
    ok &= E["with"]["102"]["111"][1][ix("assists")] == 1 and E["with"]["104"]["111"][1][ix("assists")] == 0
    # a power-play goal (NYR four skaters): ppp for the scorer and the assist, not for the even-strength ones
    ok &= E["toi"]["104"][1][ix("ppp")] == 1 and E["toi"]["112"][1][ix("ppp")] == 1 and E["toi"]["101"][1][ix("ppp")] == 0
    # an assist made before his change (105 off at 180, the goal at 190) is still his, with the team on the ice at 190
    ok &= E["toi"]["105"][1][ix("assists")] == 1 and E["with"]["106"]["105"][1][ix("assists")] == 1
    # a teammate's block is no block; a defender's is
    ok &= N["toi"]["201"][1][ix("blocks")] == 0 and E["toi"]["111"][1][ix("blocks")] == 1
    ok &= N["toi"]["203"][1][ix("attempts")] == 1 and N["toi"]["201"][1][ix("shots")] == 1 and E["toi"]["190"][1][ix("saves")] == 1
    # the team's goals with each one on the ice: 3 for EDM, against NYR's on-ice players
    ok &= E["total"][1] == 3 and N["total"][2] == 3 and E["team"]["101"][1] == 1 and N["team"]["212"][2] == 2
    ok &= E["names"]["101"] == "P 101"
    return bool(ok)


def test_parse():
    assert check_parse(O)


def check_pp(M):
    return (M.powerplay("1451", True) and not M.powerplay("1451", False) and not M.powerplay("0651", False)
            and not M.powerplay("1560", True) and M.powerplay("0641", False) and not M.powerplay("1551", True))


def test_powerplay():
    """1451: the home side has five skaters to four; 0651: the away side's sixth skater is its goalie pulled (no power
    play); 0641: pulled, six to four, still a power play."""
    assert check_pp(O)


def test_stretches_and_lines():
    pbp, sh = game()
    segs = O.stretches(sh)
    assert [(a, b) for a, b, _ in segs] == [(0, 100), (100, 120), (120, 180), (180, 200)]
    assert 212 not in segs[2][2] and 105 not in segs[3][2]
    _, lines, _ = O.parse(pbp, sh)
    L = lines["EDM"]
    assert sorted(L["F"][0]) in ([101, 102, 103], [104, 105, 106]) and len(L["F"]) == 2 and L["D"] == [[111, 112]]
    assert L["G"] == [190] and L["pp_secs"] == 60 and sorted(L["PP1"]) == [104, 105, 106, 111, 112]


def test_html_shifts():
    head = lambda n, name: f'<td align="center" class="playerHeading + border" colspan="8">{n} {name}</td>'
    row = lambda per, a, b: (f'<tr class="oddColor"><td class="x">1</td><td class="x">{per}</td><td class="x">{a} / 20:00</td>'
                             f'<td class="x">{b} / 19:16</td><td class="x">00:44</td><td class="x">&nbsp;</td></tr>')
    page = head(4, "HEISKANEN, MIRO") + row(1, "0:00", "0:44") + row(3, "19:30", "20:00") + row("OT", "1:00", "1:40") + \
        head(99, "NOBODY, X") + row(1, "1:00", "2:00")
    assert O.html_shifts(page, {4: 8480036}) == [(8480036, 0, 44), (8480036, 3570, 3600), (8480036, 3660, 3700)]


def test_build_and_lines_table():
    pbp, sh = game()
    d = pathlib.Path(tempfile.mkdtemp())
    con = O.connect(d / "o.sqlite")
    for gid, date in (("2026020001", "2026-10-10"), ("2026020002", "2026-10-12")):
        splits, lines, _ = O.parse(pbp, sh)
        O.store(con, gid, 2026, date, "json", splits, lines)
    con.commit()
    assert O.refresh_lines(con) == 2
    L = json.loads(con.execute("SELECT js FROM lines WHERE team='EDM'").fetchone()[0])
    assert L["gid"] == "2026020002" and L["G"] == [190]
    docs = O.build(con, 2026)
    e = docs["EDM"]
    assert e["games"] == 2 and e["season"] == "2026-27" and e["gp"]["101"] == 2 and e["toi"]["101"][0] == 200
    assert e["with"]["102"]["111"][1][O.S["assists"]] == 2 and e["total"][1] == 6 and e["heads"]["101"].endswith("/EDM/101.png")
    O.write(d / "out", docs)
    assert json.loads((d / "out" / "NYR.json").read_text())["team"] == "NYR"


def _mutant(path, name, old, new):
    src = pathlib.Path(path).read_text()
    assert src.count(old) == 1, (name, old)
    d = pathlib.Path(tempfile.mkdtemp())
    f = d / f"{name}.py"
    f.write_text(src.replace(old, new))
    spec = importlib.util.spec_from_file_location(name, f)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_mutants():
    """Every guard above fails its check when broken."""
    cases = [
        ("nhl_onoff_m1", 'and d.get("reason") != "teammate-blocked"', "", check_parse, "a teammate's block"),
        ("nhl_onoff_m2", "a, h = ask - (1 - ag), hsk - (1 - hg)", "a, h = ask, hsk", check_pp, "a pulled goalie is no power play"),
        ("nhl_onoff_m3", "i = bisect.bisect_left(starts, t) - 1", "i = bisect.bisect_right(starts, t) - 1", check_parse,
         "the goal at a change is the old line's"),
        ("nhl_onoff_m4", "if j is None and team and segs:", "if False:", check_parse, "an assist after his change"),
        ("nhl_onoff_m5", "pp = powerplay(e.get(\"situationCode\"), d.get(\"eventOwnerTeamId\") == home_id)",
         "pp = powerplay(e.get(\"situationCode\"), d.get(\"eventOwnerTeamId\") != home_id)", check_parse, "the scoring side"),
        ("nhl_onoff_m6", "                for y in side(segs[j][2], opp):\n                    split[opp][\"team\"][y][2] += 1",
         "                pass", check_parse, "goals against while on the ice"),
    ]
    for name, old, new, check, label in cases:
        assert not check(_mutant(O.__file__, name, old, new)), f"mutant survived: {label}"
