"""Amendment 27: the tip card (window, fresh lines, leads, minutes band, speed-card players, 2 per team-game, once
per game, the forward decision), absence games 3-4 in their own cell, and the card's price tolerance.
MUTANTS in test_mutants()."""
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

GD = "2026-10-25"
NOW = dt.datetime(2026, 10, 25, 23, 40, tzinfo=dt.timezone.utc)
STAMP = "2026-10-25T23:40:00"
GAMES = {"PHX": ("G1", "2026-10-26T00:00:00Z", "SAC @ PHX"), "SAC": ("G1", "2026-10-26T00:00:00Z", "SAC @ PHX"),
         "DEN": ("G2", "2026-10-26T00:25:00Z", "DEN @ LAC"),       # 45 min out: not yet
         "LAL": ("G3", "2026-10-26T00:00:00Z", "LAL @ POR")}       # in the window, lines 30 min old
LINES = {("G1", 1, "points"): (8.5, 1.9, "2026-10-25T23:38:00"), ("G2", 9, "points"): (8.5, 1.9, "2026-10-25T23:38:00"),
         ("G3", 7, "points"): (8.5, 1.9, "2026-10-25T23:10:00")}


def fl(team, b, pid, stat, line, margin, d_min=5.0, tier="wowy", stale="POSTED-AFTER"):
    gid, gtime, mu = GAMES[team]
    return {"tier": tier, "team": team, "x": "X", "b": b, "pid": pid, "stat": stat, "line": line, "odds": 1.9,
            "proj": line + margin, "margin": margin, "gid": gid, "gtime": gtime, "matchup": mu, "game_date": GD,
            "horizon": 0, "x_pid": 99, "d_min": d_min, "_stale": stale}


PASS = [fl("PHX", "Collin Gillespie", 1, "pts", 8.5, 9.0),            # lead, excess 1.8: tip card
        fl("PHX", "Collin Gillespie", 1, "pra", 15.5, 13.0),          # non-lead
        fl("PHX", "Ryan Dunn", 2, "reb", 3.5, 3.0, d_min=10.0),       # out of the minutes band
        fl("PHX", "Royce O'Neale", 3, "pts", 7.5, 7.5),               # lead, excess 1.5: tip card (shares P)
        fl("PHX", "Grayson Allen", 4, "reb", 4.5, 1.4),               # lead, excess 1.4: 3rd -> TEAM SLOT
        fl("PHX", "Devin Booker", 5, "pts", 24.5, 10.0, stale="STALE"),   # on the speed card already
        fl("PHX", "Nick Richards", 6, "points", 6.5, 2.0, tier="priced"),    # priced: never considered
        fl("SAC", "Keegan Murray", 10, "reb", 6.5, 1.2),              # the other team: its own 2 slots
        fl("DEN", "Christian Braun", 9, "pts", 11.5, 8.0),            # not in the window yet
        fl("LAL", "Austin Reaves", 7, "pts", 17.5, 8.0)]              # stale lines: not decided


def run(mod, sh, flags=PASS, now=NOW, stamp=STAMP, lines=LINES):
    saved = (mod._stale_of, mod.MARGIN, mod.FILTERS_ON)
    mod._stale_of = lambda f, st: f["_stale"]
    mod.MARGIN = {"pra": 5.0, "pts": 5.0, "reb": 1.0}
    mod.FILTERS_ON = False                                  # amendment 28 is tested in test_nba_filters
    why = Counter()
    try:
        _, ins = mod._log_flags(sh, flags, stamp, why)
        tip = mod._tip_card(sh, flags, GAMES, lines, now, stamp, why, GD)
    finally:
        mod._stale_of, mod.MARGIN, mod.FILTERS_ON = saved
    return ins, tip, why


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    sh = mod._shadow(pathlib.Path(tempfile.mkdtemp()) / "s.sqlite")
    ins, tip, why = run(mod, sh)
    tc = {(b, s): (c, w) for b, s, c, w in sh.execute("SELECT b, stat, card, why FROM tipcard")}
    want([f["b"] for f in ins] == ["Devin Booker"], "speed card first: Booker (STALE line) carded by the speed card")
    want(tc.get(("Collin Gillespie", "pts")) == (1, None) and tc.get(("Royce O'Neale", "pts")) == (1, None),
         "tip card: Gillespie PTS (1.8) and O'Neale PTS (1.5) carded, at lines posted after the news")
    want(tc.get(("Collin Gillespie", "pra")) == (0, "1 PER PLAYER"), "one per player: Gillespie's PRA logged only")
    want(tc.get(("Ryan Dunn", "reb")) == (0, "MINUTES OUT OF BAND"), "minutes band: Dunn d_min 10 logged only")
    want(tc.get(("Grayson Allen", "reb")) == (0, "TEAM SLOT"), "2 per team-game: Allen (3rd lead) logged only")
    want(tc.get(("Devin Booker", "pts")) == (0, "ON SPEED CARD"), "a speed-card player is not carded twice")
    want(tc.get(("Keegan Murray", "reb")) == (1, None), "the other team in the game has its own 2 slots")
    want(("Nick Richards", "points") not in tc, "priced is never considered")
    want(not any(b in ("Christian Braun", "Austin Reaves") for b, _ in tc),
         "not decided: a game 45 min out, and a game whose lines are 30 min old")
    want(why["tip_lines_stale"] == 1, "the stale-lines skip is counted")
    want(sorted((f["b"], f["tier"]) for f in tip) == [("Collin Gillespie", "wowy tip"), ("Keegan Murray", "wowy tip"),
                                                      ("Royce O'Neale", "wowy tip")], "tip plays are pinged as 'wowy tip'")
    fc = dict(sh.execute("SELECT b || ' ' || stat, card_why FROM flags WHERE card = 1"))
    want(fc == {"Devin Booker pts": None, "Collin Gillespie pts": "TIP CARD", "Royce O'Neale pts": "TIP CARD",
                "Keegan Murray reb": "TIP CARD"}, "flag rows: card 1, card_why TIP CARD")
    want(dict(sh.execute("SELECT gid, carded FROM tipcard_games")) == {"G1": 3}, "decided games: G1 only")
    _, tip2, _ = run(mod, sh, flags=[dict(f, line=f["line"] + 1) for f in PASS], now=NOW + dt.timedelta(minutes=5),
                     stamp="2026-10-25T23:45:00", lines={k: (v[0], v[1], "2026-10-25T23:44:00") for k, v in LINES.items()})
    want(not any(f["team"] in ("PHX", "SAC") for f in tip2) and sh.execute(
        "SELECT COUNT(*) FROM tipcard WHERE gid='G1'").fetchone()[0] == 7, "once per game: G1 not re-decided")
    want([f["b"] for f in tip2] == ["Austin Reaves"], "G3 decided on the next pass, once its lines are fresh")
    return ok


def test_tip_card():
    assert check(F)


def decided(db, plays):
    sh = F._shadow(db)
    for i, (gid, actual, odds, void) in enumerate(plays):
        sh.execute("INSERT INTO flags (flag_id, game_date, tier, b, stat, line, odds, actual, void_reason) "
                   "VALUES (?,?,?,?,?,?,?,?,?)", (f"f{i}", GD, "wowy", f"P{i}", "pts", 10.5, odds, actual, void))
        sh.execute("INSERT INTO tipcard (game_date, gid, flag_id, pid, b, stat, line, odds, excess, decided_at, card) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,1)", (GD, gid, f"f{i}", i, f"P{i}", "pts", 10.5, odds, 1.0,
                                                    f"2026-10-25T23:{i // 60:02d}:{i % 60:02d}"))
    sh.commit()
    return sh


def test_tip_decision():
    d = pathlib.Path(tempfile.mkdtemp())
    p = lambda n, w, odds=1.9: [(f"G{i % 20}", 12 if i < w else 8, odds, None) for i in range(n)]
    assert V.tip_decision(decided(d / "a.sqlite", p(59, 59)))["verdict"] == "accumulating (59/60)"
    assert V.tip_decision(decided(d / "b.sqlite", p(60, 31)))["verdict"].startswith("OFF")   # 31*.9-29 = -1.1u
    assert V.tip_decision(decided(d / "c.sqlite", p(60, 32)))["verdict"].startswith("ON")    # 32*.9-28 = +0.8u
    td = V.tip_decision(decided(d / "e.sqlite", p(60, 32) + p(40, 0)))                      # later plays don't count
    assert td["n"] == 60 and td["units"] == 0.8 and td["ci"] is not None, td
    voids = [(g, a, o, "premise died") for g, a, o, _ in p(10, 0)]
    assert V.tip_decision(decided(d / "f.sqlite", voids + p(59, 59)))["n"] == 59              # voids excluded
    sh = decided(d / "g.sqlite", p(60, 31))
    saved = (F._stale_of, F.MARGIN, F.FILTERS_ON)
    F._stale_of, F.MARGIN, F.FILTERS_ON = (lambda f, st: f["_stale"]), {"pra": 5.0, "pts": 5.0, "reb": 1.0}, False
    try:
        F._log_flags(sh, PASS, STAMP, Counter())
        out = F._tip_card(sh, PASS, GAMES, LINES, NOW, STAMP, Counter(), GD)
    finally:
        F._stale_of, F.MARGIN, F.FILTERS_ON = saved
    assert not out and sh.execute("SELECT COUNT(*) FROM tipcard WHERE gid='G1' AND why='TIP CARD OFF (DECISION)'"
                                  ).fetchone()[0] == 3, "decided OFF: the tip card logs only"


def test_tip_due():
    d = pathlib.Path(tempfile.mkdtemp()) / "s.sqlite"
    at = lambda m: (NOW + dt.timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sched = [{"gid": g, "status": st, "utc": at(m), "date_et": GD}
             for g, m, st in (("a", 5, 1), ("b", 5.5, 1), ("c", 30, 1), ("d", 31, 1), ("e", 20, 2), ("f", 20, 1))]
    sh = F._shadow(d)
    sh.execute("INSERT INTO tipcard_games VALUES ('f', ?, ?, 0, 0)", (GD, STAMP))
    sh.commit()
    assert F.tip_due(sched, NOW, path=d) == {"b": GD, "c": GD}      # (5, 30]; not started; not decided


def test_absence_cell_and_combo_decision():
    import io
    import contextlib
    rows = [{"tier": "wowy", "pid": 1, "stat": "pts", "game_date": GD, "gid": "G", "horizon": 0, "aidx": 3,
             "confirmed": None, "x_status": "Out", "x_min": 34.0, "logged_at": "2026-10-25T23:00:00"},
            {"tier": "wowy", "pid": 2, "stat": "pts", "game_date": GD, "gid": "G", "horizon": 0, "aidx": 2,
             "confirmed": None, "x_status": "Out", "x_min": 34.0, "logged_at": "2026-10-25T23:00:00"}]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        V.scoreboard(rows)
    out = buf.getvalue()
    assert "wowy/absence3-4 FD" in out and "wowy/h0 FD" in out
    combo = [dict(r, stat="pra", actual=30, line=20.5, odds=1.9, logged_at="2026-10-25T23:00:00") for r in rows]
    assert V.combo_decision(combo)["n"] == 1                         # absence game 3 stays outside amendment 19
    src = pathlib.Path(F.__file__).read_text()
    assert src.count("if ai is not None and ai > TRIGGER_MAX_ABSENCE:") == 2 and F.TRIGGER_MAX_ABSENCE == 4
    assert F.MAX_ABSENCE_GAME == 2                                   # the carry rule and the speed test keep 2


def quotes(db, moves):
    q = sqlite3.connect(db)
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT, "
              "stat TEXT, line REAL, side TEXT, odds REAL)")
    for t, line, o in moves:
        q.execute("INSERT INTO quotes VALUES (?, 'fd', 'G', '2026-10-26T00:00:00Z', 1, 'P', 'points', ?, 'over', ?)",
                  (t, line, o))
        q.execute("INSERT INTO quotes VALUES (?, 'fd', 'G', '2026-10-26T00:00:00Z', 1, 'P', 'points', ?, 'under', 1.95)",
                  (t, line))
    q.commit()
    return q


def test_price_tolerance():
    d = pathlib.Path(tempfile.mkdtemp())
    r = {"news_at": "2026-10-25T20:00:00Z", "pid": 1, "stat": "pts", "gid": "G", "logged_at": "2026-10-25T20:10:00"}
    toppin = quotes(d / "a.sqlite", [("2026-10-25T19:00:00", 13.5, 1.8197), ("2026-10-25T20:05:00", 13.5, 1.8696)])
    assert V.cell_stale(toppin, r) == "LATE"                          # the tracked cell keeps 0.03
    assert V.cell_stale(toppin, r, eps=F.STALE_PRICE_EPS) == "STALE"   # -122 -> -115: jitter, still stale
    big = quotes(d / "b.sqlite", [("2026-10-25T19:00:00", 13.5, 1.8197), ("2026-10-25T20:05:00", 13.5, 1.95)])
    assert V.cell_stale(big, r, eps=F.STALE_PRICE_EPS) == "LATE"
    src = pathlib.Path(F.__file__).read_text()
    assert "V.cell_stale(q, dict(f, logged_at=stamp), eps=STALE_PRICE_EPS)" in src


def test_price_jitter_measurement():
    import nba_reaction as RX
    d = pathlib.Path(tempfile.mkdtemp())
    q = quotes(d / "j.sqlite", [("2026-10-25T20:00:00", 13.5, 1.80), ("2026-10-25T20:06:00", 13.5, 1.85),
                                ("2026-10-25T20:30:00", 14.5, 1.90)])
    q.execute("CREATE TABLE cycles (ts TEXT, book TEXT, status TEXT)")
    for m in (0, 1, 7, 20, 31, 75):                  # polls; the last is outside the 60-min window
        q.execute("INSERT INTO cycles VALUES (?, 'fd', 'ok')", (f"2026-10-25T{20 + m // 60}:{m % 60:02d}:00",))
    res = [{"t0": "2026-10-25T20:00:00", "units": {"control": [{"gid": "G", "pid": 1, "stat": "points"}]}}]
    # pairs 5-15 min apart, same line, price changed: 20:00->20:07 and 20:01->20:07 (.05 each); 20:07->20:20 same
    # price; 20:20->20:31 line changed. Deduped across triggers.
    assert [round(x, 4) for x in RX.price_jitter(res + res, q)] == [0.05, 0.05]


def test_board_shows_tip_card():
    import nba_board as B
    d = pathlib.Path(tempfile.mkdtemp())
    sh = F._shadow(d / "s.sqlite")
    sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, team, x, b, stat, line, odds, gid, gtime, matchup, "
               "pid, x_pid, horizon, card, card_why) VALUES ('t', '2026-10-25T21:00:00', ?, 'wowy', 'PHX', 'X', "
               "'Collin Gillespie', 'pts', 8.5, 1.80, 'G1', '2026-10-26T00:00:00Z', 'SAC @ PHX', 1, 99, 0, 1, 'TIP CARD')", (GD,))
    sh.execute("INSERT INTO tipcard (game_date, gid, flag_id, pid, b, stat, line, odds, decided_at, card) "
               "VALUES (?, 'G1', 't', 1, 'Collin Gillespie', 'pts', 8.5, 1.95, '2026-10-25T23:31:00', 1)", (GD,))
    sh.commit()
    sqlite3.connect(d / "q.sqlite").execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, "
                                            "pid INTEGER, player TEXT, stat TEXT, line REAL, side TEXT, odds REAL)")
    saved = (B.SHADOW, B.NEWS, B.LINES)
    B.SHADOW, B.NEWS, B.LINES = d / "s.sqlite", d / "n.sqlite", d / "q.sqlite"
    try:
        b = B.board(NOW)
    finally:
        B.SHADOW, B.NEWS, B.LINES = saved
    r = b["slates"][0]["games"][0]["rows"][0]
    assert r["tiers"] == ["wowy tip"] and r["odds"] == 1.95 and r["flagged_mt"] == "5:31 PM", r
    assert "WOWY · TIP CARD" in B.html(b)


def test_mutants():
    src = pathlib.Path(F.__file__).read_text()
    for tag, a, b in (
            ("no minutes band", "            elif not (f.get(\"d_min\") is not None and DMIN_BAND[0] <= f[\"d_min\"] <= DMIN_BAND[1]):\n"
                                "                v, w = 0, \"MINUTES OUT OF BAND\"\n", ""),
            ("speed-card players carded again", "                v, w = 0, \"ON SPEED CARD\"", "                v, w = 1, None"),
            ("3 slots", "elif slots[f[\"team\"]] >= TIP_SLOTS:", "elif slots[f[\"team\"]] >= TIP_SLOTS + 1:"),
            ("slots per game, not team", "elif slots[f[\"team\"]] >= TIP_SLOTS:", "elif sum(slots.values()) >= TIP_SLOTS:"),
            ("non-leads carded", "            elif not is_lead(f):\n                v, w = 0, \"1 PER PLAYER\"\n", ""),
            ("decided every pass", "        if gid in decided or not", "        if not"),
            ("stale lines ok", "        if seen_at[gid] < cut:", "        if False:"),
            ("any time to tip", "not TIP_WINDOW_MIN[0] < mins <= TIP_WINDOW_MIN[1]", "not 0 < mins <= 60"),
            ("priced considered", "fs = [f for f in out_flags if f[\"gid\"] == gid and f[\"tier\"] == \"wowy\"]",
             "fs = [f for f in out_flags if f[\"gid\"] == gid]")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_flags_mut27.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_flags_mut27")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_flags_mut27", None)


if __name__ == "__main__":
    test_tip_card(); test_tip_decision(); test_tip_due(); test_absence_cell_and_combo_decision()
    test_price_tolerance(); test_board_shows_tip_card(); test_mutants()
    print("test_nba_tipcard: OK")
