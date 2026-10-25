"""Amendment 29: 2+ STARS OUT off both cards (after amendment 28's filters), the STARS OUT count, its forward
check, the stored value and cell, and the tip-card CLV report. MUTANTS in test_mutants()."""
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
GAMES = {"PHX": ("G1", "2026-10-27T00:00:00Z", "SAC @ PHX"), "SAC": ("G1", "2026-10-27T00:00:00Z", "SAC @ PHX")}
LINES = {("G1", 1, "points"): (8.5, 1.9, "2026-10-26T23:38:00")}


def fl(team, b, pid, stat, line, margin, stars, stale="STALE"):
    gid, gtime, mu = GAMES[team]
    return {"tier": "wowy", "team": team, "x": "X", "b": b, "pid": pid, "stat": stat, "line": line, "odds": 1.9,
            "proj": line + margin, "margin": margin, "gid": gid, "gtime": gtime, "matchup": mu, "game_date": GD,
            "horizon": 0, "x_pid": 99, "d_min": 5.0, "x_min": 30.0, "stars_out": stars, "_stale": stale}


PASS = [fl("PHX", "Collin Gillespie", 1, "pts", 8.5, 7.0, 2),        # PHX has 2 stars out: off
        fl("PHX", "Ryan Dunn", 2, "reb", 3.5, 1.5, 2),               # rebounds: amendment 28's reason comes first
        fl("SAC", "Keegan Murray", 10, "pts", 12.5, 6.0, 1),         # one star out: carded
        fl("SAC", "Malik Monk", 11, "pts", 14.5, 6.5, None)]         # unknown count: carded


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    saved = (mod._stale_of, mod.MARGIN, mod.FILTERS_ON, mod.STARS_RULE_ON)
    mod._stale_of, mod.MARGIN = (lambda f, st: f["_stale"]), {"pra": 6.5, "pts": 5.0, "reb": 1.0}
    mod.FILTERS_ON, mod.STARS_RULE_ON = True, True
    try:
        sh = mod._shadow(pathlib.Path(tempfile.mkdtemp()) / "s.sqlite")
        _, ins = mod._log_flags(sh, PASS, STAMP, Counter())
        c = {b: (v, w, so) for b, v, w, so in sh.execute("SELECT b, card, card_why, stars_out FROM flags")}
        want(c["Collin Gillespie"][:2] == (0, "2+ STARS OUT"), "speed card: 2 stars out -> off")
        want(c["Ryan Dunn"][:2] == (0, "REBOUNDS OFF CARD"), "amendment 28's filters are checked first")
        want(c["Keegan Murray"][0] == 1 and c["Malik Monk"][0] == 1, "1 star out, or an unknown count: carded")
        want(c["Collin Gillespie"][2] == 2 and c["Malik Monk"][2] is None, "stars_out stored on the flag")
        sh2 = mod._shadow(pathlib.Path(tempfile.mkdtemp()) / "s.sqlite")
        tipf = [dict(f, _stale="POSTED-AFTER") for f in PASS]
        mod._log_flags(sh2, tipf, STAMP, Counter())
        tip = mod._tip_card(sh2, tipf, GAMES, LINES, NOW, STAMP, Counter(), GD)
        t = dict(sh2.execute("SELECT b, why FROM tipcard"))
        want(t.get("Collin Gillespie") == "2+ STARS OUT" and sorted(f["b"] for f in tip) == ["Keegan Murray", "Malik Monk"],
             "tip card: the same rule")
        mod.STARS_RULE_ON = False
        sh3 = mod._shadow(pathlib.Path(tempfile.mkdtemp()) / "s.sqlite")
        mod._log_flags(sh3, PASS, STAMP, Counter())
        want(dict(sh3.execute("SELECT b, card FROM flags"))["Collin Gillespie"] == 1, "rule switched off: carded again")
        apps = {5: [(f"2026-10-{d:02d}", 34.0, {}, "PHX") for d in range(10, 25)],      # star, played 10/24
                6: [(f"2026-10-{d:02d}", 30.0, {}, "PHX") for d in range(1, 13)],       # last played 10/12: 14 days
                7: [(f"2026-10-{d:02d}", 20.0, {}, "PHX") for d in range(10, 25)],      # not a star (20 min)
                8: [(f"2026-10-{d:02d}", 28.0, {}, "PHX") for d in range(16, 25)],      # 9 apps only
                9: [(f"2026-10-{d:02d}", 25.0, {}, "PHX") for d in range(14, 25)]}      # star
        so = mod.stars_out_by_team({5: "PHX", 6: "PHX", 7: "PHX", 8: "PHX", 9: "PHX"}, apps, GD)
        want(so == Counter({"PHX": 2}), f"STARS OUT counts 24+ min, >= 10 apps, active <= 12 days (got {dict(so)})")
    finally:
        mod._stale_of, mod.MARGIN, mod.FILTERS_ON, mod.STARS_RULE_ON = saved
    return ok


def test_stars_rule():
    assert check(F)


def test_stars_decision():
    d = pathlib.Path(tempfile.mkdtemp())

    def store(db, plays):
        sh = F._shadow(db)
        for i, (at, pid, actual, stars, d_min, filt) in enumerate(plays):
            sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, b, pid, stat, line, odds, actual, stars_out, "
                       "d_min, filt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (f"f{i}", at, GD, "wowy", f"P{pid}", pid, "pts", 10.5, 1.9, actual, stars, d_min, filt))
        sh.commit()
        return sh
    at = lambda i: f"2026-10-27T{i // 60:02d}:{i % 60:02d}:00"
    p = lambda n, w: [(at(i), i, 12 if i < w else 8, 2, 5.0, None) for i in range(n)]
    assert V.stars_decision(store(d / "a.sqlite", p(39, 39)))["verdict"] == "accumulating (39/40)"
    assert V.stars_decision(store(d / "b.sqlite", p(40, 22)))["verdict"].startswith("OFF")   # 22*.9-18 = +1.8u
    assert V.stars_decision(store(d / "c.sqlite", p(40, 21)))["verdict"].startswith("ON")    # 21*.9-19 = -0.1u
    noise = [(at(100 + i), 100 + i, 12, s, dm, fi) for i, (s, dm, fi) in
             enumerate(((1, 5.0, None), (2, 9.0, None), (2, 5.0, "EDGE TOO BIG"), (None, 5.0, None)))]
    noise.append(("2026-10-25T12:00:00", 200, 12, 2, 5.0, None))                         # before the cutover
    noise.append((at(150), 0, 12, 2, 5.0, None))                                         # a re-flag of play 0
    assert V.stars_decision(store(d / "e.sqlite", p(39, 39) + noise))["n"] == 39
    assert F._stars_rule_on(d / "b.sqlite") is False and F._stars_rule_on(d / "c.sqlite") is True
    assert F._stars_rule_on(d / "missing.sqlite") is True
    assert "    STARS_RULE_ON = _stars_rule_on(SHADOW)" in pathlib.Path(F.__file__).read_text()


def test_tip_clv():
    d = pathlib.Path(tempfile.mkdtemp())
    sh = F._shadow(d / "s.sqlite")
    q = sqlite3.connect(d / "q.sqlite")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT, "
              "stat TEXT, line REAL, side TEXT, odds REAL)")
    for t, pid, line, o in (("2026-01-09T23:20:00", 1, 18.5, 1.83), ("2026-01-09T23:55:00", 1, 19.5, 1.90),
                            ("2026-01-09T23:20:00", 2, 12.5, 1.90), ("2026-01-09T23:55:00", 2, 12.5, 1.95)):
        for side, oo in (("over", o), ("under", 1.9)):
            q.execute("INSERT INTO quotes VALUES (?, 'fd', 'G', '2026-01-10T00:00:00Z', ?, 'P', ?, ?, ?, ?)",
                      (t, pid, "pra" if pid == 1 else "points", line, side, oo))
    for fid, pid, stat, line, odds in (("a", 1, "pra", 18.5, 1.83), ("b", 2, "pts", 12.5, 1.90)):
        sh.execute("INSERT INTO flags (flag_id, game_date, tier, pid, stat, line, odds, gtime) VALUES "
                   "(?, '2026-01-09', 'wowy', ?, ?, ?, ?, '2026-01-10T00:00:00Z')", (fid, pid, stat, line, odds))
        sh.execute("INSERT INTO tipcard (gid, flag_id, pid, stat, line, odds, decided_at, card) VALUES "
                   "('G', ?, ?, ?, ?, ?, '2026-01-09T23:30:00', 1)", (fid, pid, stat, line, odds))
    sh.commit(); q.commit()
    out = V.tip_clv(sh, q)
    assert out == {"n": 2, "fd_n": 2, "fd_beat": 1, "moved": 1.0, "dec_n": 2, "dec_beat": 1}, out


def test_stars_cell():
    d = pathlib.Path(tempfile.mkdtemp())
    sh = F._shadow(d / "s.sqlite")
    for fid, pid, stars in (("a", 1, 2), ("b", 2, 1), ("c", 3, None)):
        sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, b, pid, stat, line, odds, gid, gtime, stars_out) "
                   "VALUES (?, '2026-01-09T13:00:00', ?, 'wowy', 'P', ?, 'pts', 10.5, 1.9, 'G', '2026-01-10T00:00:00Z', ?)",
                   (fid, GD, pid, stars))
    sh.commit()
    sqlite3.connect(d / "q.sqlite").execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, "
                                            "pid INTEGER, player TEXT, stat TEXT, line REAL, side TEXT, odds REAL)")
    saved = (V.SHADOW, V.LINES, V.NEWS, V.AMEND8_CUTOVER, V.AMEND29_CUTOVER)
    V.SHADOW, V.LINES, V.NEWS = d / "s.sqlite", d / "q.sqlite", d / "n.sqlite"
    V.AMEND8_CUTOVER = V.AMEND29_CUTOVER = "2026-01-09T12:00:00"
    try:
        rows = {r["flag_id"]: r for r in V.collect()}
    finally:
        V.SHADOW, V.LINES, V.NEWS, V.AMEND8_CUTOVER, V.AMEND29_CUTOVER = saved
    assert [rows[k]["cells"]["STARS OUT (29)"] for k in "abc"] == ["2+", "1", "1"]


def test_mutants():
    src = pathlib.Path(F.__file__).read_text()
    for tag, a, b in (
            ("no rule", "    if STARS_RULE_ON and f[\"tier\"] == \"wowy\" and (f.get(\"stars_out\") or 0) >= 2:\n"
                        "        return \"2+ STARS OUT\"\n", ""),
            ("3+ stars", "(f.get(\"stars_out\") or 0) >= 2:", "(f.get(\"stars_out\") or 0) >= 3:"),
            ("switch ignored", "    if STARS_RULE_ON and f[\"tier\"] == \"wowy\"", "    if f[\"tier\"] == \"wowy\""),
            ("any absence counts", "        if (len(xa) >= 10 and _mean_last10(xa) >= WOWY_STAR_MIN\n"
                                   "                and (gday - dt.date.fromisoformat(xa[-1][0])).days <= ACTIVE_DAYS):",
             "        if xa:"),
            ("no activity check", " and (gday - dt.date.fromisoformat(xa[-1][0])).days <= ACTIVE_DAYS):", "):"),
            ("rule before filters", "    if _filtered(f):\n        return _filtered(f)\n    if STARS_RULE_ON",
             "    if STARS_RULE_ON and (f.get(\"stars_out\") or 0) >= 2 and f[\"tier\"] == \"wowy\":\n"
             "        return \"2+ STARS OUT\"\n    if _filtered(f):\n        return _filtered(f)\n    if STARS_RULE_ON")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_flags_mut29.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_flags_mut29")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_flags_mut29", None)


if __name__ == "__main__":
    test_stars_rule(); test_stars_decision(); test_tip_clv(); test_stars_cell(); test_mutants()
    print("test_nba_stars: OK")
