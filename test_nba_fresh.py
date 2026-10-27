"""Amendment 31: fresh news only. A play is carded (speed card or tip card) and pinged only within FRESH_MIN
minutes of its news_at; older or missing news is logged only as NEWS NOT FRESH. The 15:00 boundary, the news
time formats (report, X with microseconds, an offset), sticky re-flags, recard, and the switch.
MUTANTS in test_mutants()."""
import datetime as dt
import importlib
import pathlib
import sys
import tempfile
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_flags as F

GD = "2026-10-26"
NOW = dt.datetime(2026, 10, 26, 23, 40, tzinfo=dt.timezone.utc)
STAMP = "2026-10-26T23:40:00"
GAMES = {"PHX": ("G1", "2026-10-27T00:00:00Z", "SAC @ PHX"), "MIN": ("G2", "2026-10-27T00:00:00Z", "TOR @ MIN")}
LINES = {("G1", 1, "points"): (8.5, 1.9, "2026-10-26T23:38:00"), ("G2", 9, "points"): (8.5, 1.9, "2026-10-26T23:38:00")}


def fl(team, b, pid, line, margin, news_at, stale="STALE"):
    gid, gtime, mu = GAMES[team]
    return {"tier": "wowy", "team": team, "x": "X", "b": b, "pid": pid, "stat": "pts", "line": line, "odds": 1.9,
            "proj": line + margin, "margin": margin, "gid": gid, "gtime": gtime, "matchup": mu, "game_date": GD,
            "horizon": 0, "x_pid": 99, "d_min": 5.0, "news_at": news_at, "_stale": stale}


# pts margin 5: excess = margin / 5. Without the rule, the best excess goes first and O'Neale, Dosunmu, Reid would card.
PASS = [fl("PHX", "Royce O'Neale", 3, 7.5, 8.0, "2026-10-26T23:24:59+00:00"),         # 15:01 old: not fresh
        fl("PHX", "Collin Gillespie", 1, 8.5, 7.0, "2026-10-26T23:37:04+00:00"),      # 3 min: carded
        fl("PHX", "Ryan Dunn", 2, 6.5, 6.5, "2026-10-26T23:25:00+00:00"),             # exactly 15:00: carded
        fl("PHX", "Grayson Allen", 4, 4.5, 9.0, "2026-10-26T23:39:00+00:00", stale="LATE"),   # fresh, line moved
        fl("MIN", "Ayo Dosunmu", 9, 12.5, 9.0, None),                                  # no news time
        fl("MIN", "Naz Reid", 10, 13.5, 8.5, "2026-10-26T21:15:04+00:00"),            # 2h25 old (a 2nd report)
        fl("MIN", "Rudy Gobert", 11, 10.5, 6.0, "2026-10-26T23:31:12.123456+00:00"),  # X format: carded
        fl("MIN", "Mike Conley", 12, 7.5, 5.5, "2026-10-26T19:30:00-04:00")]          # 23:30 UTC: carded
CARDED = {"Collin Gillespie", "Ryan Dunn", "Rudy Gobert", "Mike Conley"}


def run(mod, fn):
    saved = (mod._stale_of, mod.MARGIN, mod.FILTERS_ON)
    mod._stale_of = lambda f, st: f["_stale"]
    mod.MARGIN = {"pra": 6.5, "pts": 5.0, "reb": 1.0}
    mod.FILTERS_ON = False                                  # amendment 28 is tested in test_nba_filters
    try:
        return fn()
    finally:
        mod._stale_of, mod.MARGIN, mod.FILTERS_ON = saved


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    d = pathlib.Path(tempfile.mkdtemp())
    sh = mod._shadow(d / "s.sqlite")
    _, ins = run(mod, lambda: mod._log_flags(sh, PASS, STAMP, Counter()))
    c = {b: (v, w) for b, v, w in sh.execute("SELECT b, card, card_why FROM flags")}
    want({b for b, (v, _) in c.items() if v == 1} == CARDED and {f["b"] for f in ins} == CARDED,
         "speed card: only plays within 15 min of their news are carded and pinged")
    want(c["Royce O'Neale"] == (0, "NEWS NOT FRESH") and c["Ryan Dunn"][0] == 1, "boundary: 15:00 fresh, 15:01 not")
    want(c["Ayo Dosunmu"] == (0, "NEWS NOT FRESH") and c["Naz Reid"] == (0, "NEWS NOT FRESH"),
         "no news time, or news 2 h old: logged only")
    want(c["Grayson Allen"] == (0, "LINE ALREADY MOVED"), "the stale-line check still comes first")
    want(len(c) == len(PASS), "every flag is still logged")
    later = [dict(f, line=f["line"] + 1) for f in PASS if f["b"] in ("Collin Gillespie", "Royce O'Neale")]
    _, ins2 = run(mod, lambda: mod._log_flags(sh, later, "2026-10-27T00:00:00", Counter()))
    c2 = {(b, l): v for b, l, v in sh.execute("SELECT b, line, card FROM flags")}
    want(c2[("Collin Gillespie", 9.5)] == 1 and c2[("Royce O'Neale", 8.5)] == 0 and [f["b"] for f in ins2] == ["Collin Gillespie"],
         "sticky: a re-flag 23 min after the news inherits its play's card (on stays on, off stays off)")
    sh2 = mod._shadow(d / "t.sqlite")
    tipf = [dict(f, _stale="POSTED-AFTER") for f in PASS]

    def tip_pass():
        mod._log_flags(sh2, tipf, STAMP, Counter())
        return mod._tip_card(sh2, tipf, GAMES, LINES, NOW, STAMP, Counter(), GD)
    tip = run(mod, tip_pass)
    t = {b: (v, w) for b, v, w in sh2.execute("SELECT b, card, why FROM tipcard")}
    want({f["b"] for f in tip} == {"Grayson Allen", "Collin Gillespie", "Rudy Gobert", "Mike Conley"}
         and t["Ryan Dunn"] == (0, "TEAM SLOT"), "tip card: fresh leads carded (Allen, Gillespie fill PHX's 2 slots)")
    want(t["Royce O'Neale"] == (0, "NEWS NOT FRESH") and t["Naz Reid"] == (0, "NEWS NOT FRESH")
         and t["Ayo Dosunmu"] == (0, "NEWS NOT FRESH"), "tip card: older or missing news logged only")
    sh3 = mod._shadow(d / "r.sqlite")
    for fid, at, b, pid, news in (("new", "2026-10-26T23:40:00", "Fresh Play", 1, "2026-10-26T23:30:04+00:00"),
                                  ("old", "2026-10-26T23:40:00", "Late Play", 2, "2026-10-26T20:00:04+00:00")):
        sh3.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, team, b, stat, line, margin, pid, d_min, gid, "
                    "news_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (fid, at, GD, "wowy", "PHX", b, "pts", 8.5, 7.0, pid,
                                                                    5.0, "G1", news))
    sh3.commit()
    saved = mod._stale_of
    mod._stale_of = lambda f, st: "STALE"
    try:
        rc = {fid: (v, w) for fid, _b, _s, _l, v, w in mod.recard([GD], path=d / "r.sqlite")}
    finally:
        mod._stale_of = saved
    want(rc == {"new": (1, None), "old": (0, "NEWS NOT FRESH")}, f"recard: news age judged at each flag's own time ({rc})")
    mod.FRESH_RULE_ON = False
    try:
        sh4 = mod._shadow(d / "u.sqlite")
        run(mod, lambda: mod._log_flags(sh4, PASS, STAMP, Counter()))
        c4 = dict(sh4.execute("SELECT b, card FROM flags"))
    finally:
        mod.FRESH_RULE_ON = True
    want(c4["Royce O'Neale"] == 1 and c4["Ayo Dosunmu"] == 1, "rule switched off: carded on the earlier rules")
    return ok


def test_fresh():
    assert F.FRESH_RULE_ON and F.FRESH_MIN == 15.0
    assert check(F)


def test_mutants():
    src = pathlib.Path(F.__file__).read_text()
    for tag, a, b in (
            ("speed card ignores news age", "    if FRESH_RULE_ON and not _fresh(f, stamp):          # amendment 31\n"
                                            "        return 0, \"NEWS NOT FRESH\"\n", ""),
            ("tip card ignores news age", "            elif FRESH_RULE_ON and not _fresh(f, stamp):     # amendment 31\n"
                                          "                v, w = 0, \"NEWS NOT FRESH\"\n", ""),
            ("boundary exclusive", ".total_seconds() / 60 <= FRESH_MIN", ".total_seconds() / 60 < FRESH_MIN"),
            ("60-minute window", "FRESH_RULE_ON, FRESH_MIN = True, 15.0", "FRESH_RULE_ON, FRESH_MIN = True, 60.0"),
            ("missing news is fresh", "    if not f.get(\"news_at\") or not stamp:\n        return False",
             "    if not f.get(\"news_at\") or not stamp:\n        return True"),
            ("offset ignored", "dt.datetime.fromisoformat(V._utc_naive(iso))", "dt.datetime.fromisoformat(str(iso)[:19])"),
            ("switch ignored", "    if FRESH_RULE_ON and not _fresh(f, stamp):          # amendment 31",
             "    if not _fresh(f, stamp):          # amendment 31"),
            ("live pass ignores stamp", "stale=_stale_of(f, stamp), stamp=stamp)", "stale=_stale_of(f, stamp))"),
            ("recard ignores stamp", "stale=_stale_of(f, at), stamp=at)", "stale=_stale_of(f, at))")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_flags_mut31.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_flags_mut31")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_flags_mut31", None)


if __name__ == "__main__":
    test_fresh(); test_mutants()
    print("test_nba_fresh: OK")
