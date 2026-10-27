"""Amendment 28: the four card filters (edge cap, rebounds off, 32+ min stars, prices shorter than 1.80) on both
cards, the lead chosen among plays that pass, the stored FILTER value, and the forward decision that switches
them off. MUTANTS in test_mutants()."""
import datetime as dt
import importlib
import pathlib
import sqlite3
import sys
import tempfile
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_clv as V
import nba_flags as F

GD = "2026-10-26"
NOW = dt.datetime(2026, 10, 26, 23, 40, tzinfo=dt.timezone.utc)
STAMP = "2026-10-26T23:40:00"
GAMES = {"PHX": ("G1", "2026-10-27T00:00:00Z", "SAC @ PHX"), "MIN": ("G2", "2026-10-27T00:00:00Z", "TOR @ MIN")}
LINES = {("G1", 1, "points"): (8.5, 1.9, "2026-10-26T23:38:00"), ("G2", 9, "points"): (8.5, 1.9, "2026-10-26T23:38:00")}


def fl(team, b, pid, stat, line, margin, odds=1.9, x_min=30.0, stale="STALE"):
    gid, gtime, mu = GAMES[team]
    return {"tier": "wowy", "team": team, "x": "X", "b": b, "pid": pid, "stat": stat, "line": line, "odds": odds,
            "proj": line + margin, "margin": margin, "gid": gid, "gtime": gtime, "matchup": mu, "game_date": GD,
            "horizon": 0, "x_pid": 99, "d_min": 5.0, "x_min": x_min, "_stale": stale}


# margins pts 5 / reb 1 / pra 6.5 (amendment 23)
SPEED = [fl("PHX", "Collin Gillespie", 1, "reb", 3.5, 1.5),                # his best single (1.5): rebounds, off
         fl("PHX", "Collin Gillespie", 1, "pts", 8.5, 7.0),                # excess 1.4: his lead among plays that pass
         fl("PHX", "Ryan Dunn", 2, "pts", 6.5, 10.0),                      # excess 2.0: EDGE TOO BIG
         fl("PHX", "Royce O'Neale", 3, "pts", 7.5, 6.0, odds=1.79),        # PRICE -125 OR SHORTER
         fl("MIN", "Ayo Dosunmu", 9, "pts", 12.5, 6.0, x_min=32.0),        # STAR 32+ MIN
         fl("MIN", "Naz Reid", 10, "pts", 13.5, 9.5, x_min=31.9, odds=1.80)]   # excess 1.9, 31.9 min, 1.80: carded


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    saved = (mod._stale_of, mod.MARGIN, mod.FILTERS_ON, mod.FRESH_RULE_ON)
    mod.FRESH_RULE_ON = False                               # amendment 31 is tested in test_nba_fresh
    mod._stale_of, mod.MARGIN, mod.FILTERS_ON = (lambda f, st: f["_stale"]), {"pra": 6.5, "pts": 5.0, "reb": 1.0}, True
    try:
        sh = mod._shadow(pathlib.Path(tempfile.mkdtemp()) / "s.sqlite")
        _, ins = mod._log_flags(sh, SPEED, STAMP, Counter())
        c = {(b, s): (v, w, f) for b, s, v, w, f in sh.execute("SELECT b, stat, card, card_why, filt FROM flags")}
        want(c[("Collin Gillespie", "pts")][0] == 1 and c[("Collin Gillespie", "reb")][:2] == (0, "REBOUNDS OFF CARD"),
             "rebounds off; the lead is chosen among plays that pass: Gillespie PTS carded, not blocked by his REB")
        want(c[("Ryan Dunn", "pts")][:2] == (0, "EDGE TOO BIG"), "excess 2.0 -> EDGE TOO BIG")
        want(c[("Royce O'Neale", "pts")][:2] == (0, "PRICE -125 OR SHORTER"), "price 1.79 -> off")
        want(c[("Ayo Dosunmu", "pts")][:2] == (0, "STAR 32+ MIN"), "absent player at 32.0 min -> off")
        want(c[("Naz Reid", "pts")][0] == 1, "boundaries pass: excess 1.9, 31.9 min, price 1.80")
        want(sorted(f["b"] for f in ins) == ["Collin Gillespie", "Naz Reid"], "only the two that pass are pinged")
        want(c[("Ryan Dunn", "pts")][2] == "EDGE TOO BIG" and c[("Naz Reid", "pts")][2] is None,
             "the rule's verdict is stored on each flag (filt)")
        # the tip card: same filters, same lead rule (non-stale lines, a fresh store)
        sh2 = mod._shadow(pathlib.Path(tempfile.mkdtemp()) / "s.sqlite")
        tipf = [dict(f, _stale="POSTED-AFTER") for f in SPEED]
        mod._log_flags(sh2, tipf, STAMP, Counter())
        tip = mod._tip_card(sh2, tipf, GAMES, LINES, NOW, STAMP, Counter(), GD)
        t = {(b, s): (v, w) for b, s, v, w in sh2.execute("SELECT b, stat, card, why FROM tipcard")}
        want(sorted(f["b"] for f in tip) == ["Collin Gillespie", "Naz Reid"] and t[("Collin Gillespie", "reb")] ==
             (0, "REBOUNDS OFF CARD") and t[("Ryan Dunn", "pts")] == (0, "EDGE TOO BIG"),
             "tip card: the same filters and lead rule")
        # the decision switched them off: amendment 27's rules again
        mod.FILTERS_ON = False
        sh3 = mod._shadow(pathlib.Path(tempfile.mkdtemp()) / "s.sqlite")
        _, ins3 = mod._log_flags(sh3, SPEED, STAMP, Counter())
        c3 = {(b, s): (v, f) for b, s, v, f in sh3.execute("SELECT b, stat, card, filt FROM flags")}
        want(c3[("Collin Gillespie", "reb")] == (1, "REBOUNDS OFF CARD") and c3[("Ryan Dunn", "pts")][0] == 1,
             "filters off: rebounds and big edges are carded again; filt is still stored")
    finally:
        mod._stale_of, mod.MARGIN, mod.FILTERS_ON, mod.FRESH_RULE_ON = saved
    return ok


def test_filters():
    assert check(F)


def store(db, plays, cut=V.AMEND28_CUTOVER):
    sh = F._shadow(db)
    for i, (at, pid, stat, actual, odds, tip_odds) in enumerate(plays):
        sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, b, pid, stat, line, odds, actual, card) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,1)", (f"f{i}", at, GD, "wowy", f"P{pid}", pid, stat, 10.5, odds, actual))
        if tip_odds:
            sh.execute("INSERT INTO tipcard (flag_id, card, odds) VALUES (?, 1, ?)", (f"f{i}", tip_odds))
    sh.commit()
    return sh


def test_filter_decision():
    d = pathlib.Path(tempfile.mkdtemp())
    after = lambda i: f"2026-10-26T{i // 60:02d}:{i % 60:02d}:00"
    p = lambda n, w, odds=1.9: [(after(i), i, "pts", 12 if i < w else 8, odds, None) for i in range(n)]
    assert V.filter_decision(store(d / "a.sqlite", p(59, 59)))["verdict"] == "accumulating (59/60)"
    assert V.filter_decision(store(d / "b.sqlite", p(60, 31)))["verdict"].startswith("OFF")      # 31*.9-29 = -1.1u
    assert V.filter_decision(store(d / "c.sqlite", p(60, 32)))["verdict"].startswith("ON")       # +0.8u
    assert V.filter_decision(store(d / "e.sqlite", p(60, 32) + [(after(70 + i), 100 + i, "pts", 8, 1.9, None)
                                                                for i in range(40)]))["units"] == 0.8   # first 60 only
    dup = p(59, 59) + [(after(65), 0, "pts", 8, 1.9, None)]                       # a re-flag of play 0: one per play
    assert V.filter_decision(store(d / "f.sqlite", dup))["n"] == 59
    before = [("2026-10-25T10:00:00", 500, "pts", 8, 1.9, None)] + p(59, 59)
    assert V.filter_decision(store(d / "g.sqlite", before))["n"] == 59          # before the cutover: not counted
    tipp = [(after(i), i, "pts", 12, 1.9, 1.5) for i in range(60)]              # tip plays at their decided price
    assert V.filter_decision(store(d / "h.sqlite", tipp))["units"] == 30.0
    assert F._filters_on(d / "b.sqlite") is False and F._filters_on(d / "c.sqlite") is True
    assert F._filters_on(d / "missing.sqlite") is True
    src = pathlib.Path(F.__file__).read_text()
    assert "    FILTERS_ON = _filters_on(SHADOW)" in src                       # read at the start of every pass


def test_filter_cell():
    d = pathlib.Path(tempfile.mkdtemp())
    sh = F._shadow(d / "s.sqlite")
    for fid, pid, tier, filt in (("a", 1, "wowy", "REBOUNDS OFF CARD"), ("b", 2, "wowy", None), ("c", 3, "priced", None)):
        sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, b, pid, stat, line, odds, gid, gtime, filt) "
                   "VALUES (?, '2026-01-09T13:00:00', ?, ?, 'P', ?, 'pts', 10.5, 1.9, 'G', '2026-01-10T00:00:00Z', ?)",
                   (fid, GD, tier, pid, filt))
    sh.commit()
    sqlite3.connect(d / "q.sqlite").execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, "
                                            "pid INTEGER, player TEXT, stat TEXT, line REAL, side TEXT, odds REAL)")
    saved = (V.SHADOW, V.LINES, V.NEWS, V.AMEND8_CUTOVER, V.AMEND28_CUTOVER)
    V.SHADOW, V.LINES, V.NEWS = d / "s.sqlite", d / "q.sqlite", d / "n.sqlite"
    V.AMEND8_CUTOVER, V.AMEND28_CUTOVER = "2026-01-09T12:00:00", "2026-01-09T12:00:00"   # a closed game, after both
    try:
        rows = {r["flag_id"]: r for r in V.collect()}
    finally:
        V.SHADOW, V.LINES, V.NEWS, V.AMEND8_CUTOVER, V.AMEND28_CUTOVER = saved
    assert rows["a"]["cells"]["FILTER (28)"] == "REBOUNDS OFF CARD" and rows["b"]["cells"]["FILTER (28)"] == "PASS"
    assert "FILTER (28)" not in rows["c"]["cells"]


def test_mutants():
    src = pathlib.Path(F.__file__).read_text()
    for tag, a, b in (
            ("no edge cap", "    if _excess(f) >= FILTER_EXCESS_MAX:\n        return \"EDGE TOO BIG\"\n", ""),
            ("edge cap exclusive", "if _excess(f) >= FILTER_EXCESS_MAX:", "if _excess(f) > FILTER_EXCESS_MAX:"),
            ("rebounds carded", "    if f[\"stat\"] in (\"reb\", \"rebounds\"):\n        return \"REBOUNDS OFF CARD\"\n", ""),
            ("stars carded", "f[\"x_min\"] >= FILTER_STAR_MAX:", "f[\"x_min\"] > FILTER_STAR_MAX + 9:"),
            ("short prices carded", "f[\"odds\"] < FILTER_PRICE_MIN:", "f[\"odds\"] < 1.0:"),
            ("lead among all plays", "        if f[\"tier\"] == \"priced\" or _off_card(f):", "        if f[\"tier\"] == \"priced\":"),
            ("speed card unfiltered", "    off = _off_card(f)                                  # amendments 28-29\n    if off:\n        return 0, off\n", ""),
            ("tip card unfiltered", "            if _off_card(f):                                # amendments 28-29\n                v, w = 0, _off_card(f)\n            elif",
             "            if False:\n                pass\n            elif"),
            ("switch ignored", "def _filtered(f):\n    return _filter_reason(f) if FILTERS_ON else None",
             "def _filtered(f):\n    return _filter_reason(f)")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_flags_mut28.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_flags_mut28")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_flags_mut28", None)


if __name__ == "__main__":
    test_filters(); test_filter_decision(); test_filter_cell(); test_mutants()
    print("test_nba_filters: OK")
