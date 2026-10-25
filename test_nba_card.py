"""Amendments 18-19: the card (singles first since 19). Tonight's cases (Santos PRA/PTS/REB, Brooks + Gillespie PTS, Murray priced +
wowy): one per player, top-2 disjoint per team-game per tier, sticky re-flags, pings only for the card,
the board shows only the card, and the backfill. MUTANTS in test_mutants()."""
import importlib
import pathlib
import sys
import tempfile
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_flags as F

GD = "2026-10-24"


def fl(tier, team, b, pid, stat, line, margin, d_min=5.0):
    return {"tier": tier, "team": team, "x": "X", "b": b, "pid": pid, "stat": stat, "line": line, "odds": 1.9,
            "proj": line + margin, "margin": margin, "gid": f"G{team}", "gtime": "2026-10-25T02:00:00Z",
            "matchup": team, "game_date": GD, "horizon": 0, "x_pid": 9, "d_min": d_min}


PASS1 = [fl("wowy", "GSW", "Gui Santos", 1, "reb", 5.5, 2.7), fl("wowy", "GSW", "Gui Santos", 1, "pts", 13.5, 6.8),
         fl("wowy", "GSW", "Gui Santos", 1, "pra", 21.5, 11.9),
         fl("wowy", "PHX", "Dillon Brooks", 2, "pts", 16.5, 3.2), fl("wowy", "PHX", "Collin Gillespie", 3, "pts", 8.5, 3.4),
         fl("wowy", "DEN", "Jamal Murray", 4, "pra", 35.5, 7.4), fl("wowy", "DEN", "Jamal Murray", 4, "pts", 23.5, 6.0),
         fl("priced", "DEN", "Jamal Murray", 4, "pts_ast", 31.5, 2.1)]
PASS2 = [fl("wowy", "PHX", "Collin Gillespie", 3, "pts", 9.5, 3.1),      # re-flag, moved line: stays carded
         fl("wowy", "GSW", "Gui Santos", 1, "reb", 6.5, 2.1),            # re-flag of a logged-only play
         fl("wowy", "PHX", "Grayson Allen", 5, "reb", 3.5, 2.5),         # REB too, lower excess (1.25)
         fl("wowy", "PHX", "Devin Booker", 6, "reb", 4.5, 4.0),          # REB, excess 2.0: best first
         fl("wowy", "PHX", "Royce O'Neale", 7, "pra", 9.5, 9.0),         # excess 1.8, shares P and R
         fl("wowy", "PHX", "Ryan Dunn", 8, "ast", 2.5, 3.0),             # AST shares nothing: only the cap stops it
         fl("wowy", "LAL", "LeBron James", 10, "pts", 24.5, 9.0),        # LAL lead, excess 3.0: carded
         fl("wowy", "LAL", "Austin Reaves", 11, "pts", 17.5, 6.0),       # his lead (2.0): blocked, shares P
         fl("wowy", "LAL", "Austin Reaves", 11, "reb", 4.5, 2.0)]        # non-lead: logged only, no fallback


def cards(sh):
    return {(b, stat, line): c for b, stat, line, c in sh.execute("SELECT b, stat, line, card FROM flags")}


def check(mod):
    ok = True
    saved = (mod.MARGIN, mod._stale_of)

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    sh = mod._shadow(pathlib.Path(tempfile.mkdtemp()) / "s.sqlite")
    mod._stale_of = lambda f, stamp: f.get("_stale", "STALE")          # amendment 22 is tested separately
    mod.MARGIN = {"pra": 5.0, "pts": 3.0, "reb": 2.0}                  # the card logic, on fixed margins
    why = Counter()
    _, pinged1 = mod._log_flags(sh, PASS1, "2026-10-24T22:11:52", why)
    c = cards(sh)
    want(c[("Gui Santos", "pts", 13.5)] == 1 and c[("Gui Santos", "pra", 21.5)] == 0 and c[("Gui Santos", "reb", 5.5)] == 0,
         "singles first: Santos PTS (2.27) carded over his PRA (2.38, a combo); REB (1.35) logged only")
    want(c[("Collin Gillespie", "pts", 8.5)] == 1 and c[("Dillon Brooks", "pts", 16.5)] == 0,
         "no shared component: Gillespie PTS (1.13) carded, Brooks PTS (1.07) logged only")
    want(c[("Jamal Murray", "pts_ast", 31.5)] == 1 and c[("Jamal Murray", "pra", 35.5)] == 0
         and c[("Jamal Murray", "pts", 23.5)] == 0, "priced first: Murray's priced P+A carded, his wowy plays not")
    want(sorted((f["b"], f["stat"]) for f in pinged1) ==
         [("Collin Gillespie", "pts"), ("Gui Santos", "pts"), ("Jamal Murray", "pts_ast")],
         "only the card is pinged")
    want(len(list(sh.execute("SELECT 1 FROM flags"))) == 8, "the record still logs every flag (8 of 8)")
    _, pinged2 = mod._log_flags(sh, PASS2, "2026-10-24T22:21:52", why)
    c = cards(sh)
    want(c[("Collin Gillespie", "pts", 9.5)] == 1 and c[("Gui Santos", "reb", 6.5)] == 0,
         "sticky: re-flags inherit their play's card value (on stays on, off stays off)")
    want(c[("Devin Booker", "reb", 4.5)] == 1 and c[("Grayson Allen", "reb", 3.5)] == 0,
         "best first + no shared component: Booker REB (2.0) takes PHX's 2nd slot, Allen REB (1.25) does not")
    want(c[("Royce O'Neale", "pra", 9.5)] == 0 and c[("Ryan Dunn", "ast", 2.5)] == 0,
         "top-2: O'Neale PRA (his lead: no single) and Dunn AST (disjoint) find PHX's 2 wowy slots full")
    want(c[("LeBron James", "pts", 24.5)] == 1 and c[("Austin Reaves", "pts", 17.5)] == 0
         and c[("Austin Reaves", "reb", 4.5)] == 0,
         "lead or nothing: Reaves' PTS lead is blocked by LeBron's PTS, and his REB does not stand in")
    want(sorted(f["b"] for f in pinged2) == ["Collin Gillespie", "Devin Booker", "LeBron James"],
         "pass 2 pings Booker (new) and the Gillespie re-flag (deduped downstream by nba_ping)")
    mod.MARGIN, mod._stale_of = saved
    return ok


def test_card():
    assert check(F)


def check22(mod):
    ok = True
    saved = (mod.MARGIN, mod._stale_of)

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    sh = mod._shadow(pathlib.Path(tempfile.mkdtemp()) / "s.sqlite")
    mod._stale_of = lambda f, stamp: f["_stale"]
    mod.MARGIN = {"pra": 5.0, "pts": 3.0, "reb": 2.0}                  # the card logic, on fixed margins
    flags = [dict(fl("priced", "DAL", "Max Christie", 1, "points", 11.5, 1.9), _stale="STALE"),
             dict(fl("priced", "DEN", "Aaron Gordon", 2, "reb_ast", 9.5, 1.1), _stale="POSTED-AFTER"),
             dict(fl("wowy", "PHX", "Collin Gillespie", 3, "pts", 8.5, 3.4, d_min=4.0), _stale="STALE"),
             dict(fl("wowy", "GSW", "Gui Santos", 4, "pts", 13.5, 6.8, d_min=13.1), _stale="STALE"),
             dict(fl("wowy", "GSW", "Gary Payton II", 5, "pts", 8.5, 4.5, d_min=5.1), _stale="LATE"),
             dict(fl("wowy", "DEN", "Jamal Murray", 6, "pts", 23.5, 6.0, d_min=2.4), _stale="STALE")]
    _, pinged = mod._log_flags(sh, flags, "2026-10-24T22:11:52", Counter())
    c = cards(sh)
    want(c[("Max Christie", "points", 11.5)] == 1 and c[("Aaron Gordon", "reb_ast", 9.5)] == 0,
         "stale-line card: priced on a STALE line carded, on a line posted after the news logged only")
    want(c[("Collin Gillespie", "pts", 8.5)] == 1 and c[("Gary Payton II", "pts", 8.5)] == 0,
         "stale-line card: wowy STALE carded, LATE (FD already moved) logged only")
    want(c[("Gui Santos", "pts", 13.5)] == 0 and c[("Jamal Murray", "pts", 23.5)] == 0,
         "minutes gate: wowy d_min 13.1 and 2.4 logged only (band 3-8)")
    want(sorted(f["b"] for f in pinged) == ["Collin Gillespie", "Max Christie"], "only the two carded are pinged")
    _, again = mod._log_flags(sh, [dict(flags[4], line=9.5, _stale="STALE")], "2026-10-24T23:00:00", Counter())
    want(not again and cards(sh)[("Gary Payton II", "pts", 9.5)] == 0,
         "sticky: a later STALE re-flag of an off-card play stays off (and is not pinged)")
    mod.MARGIN, mod._stale_of = saved
    return ok


def test_card_22():
    assert check22(F)


def test_backfill_matches_live():
    d = pathlib.Path(tempfile.mkdtemp())
    sh = F._shadow(d / "s.sqlite")
    for i, f in enumerate(PASS1):                       # as logged before the card existed: card NULL
        sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, team, b, stat, line, margin, pid) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?)", (f"f{i}", "2026-10-24T22:11:52", GD, f["tier"], f["team"], f["b"],
                                                    f["stat"], f["line"], f["margin"], f["pid"]))
    sh.commit()
    saved, F.MARGIN = F.MARGIN, {"pra": 5.0, "pts": 3.0, "reb": 2.0}
    try:
        F.card_backfill([GD], path=d / "s.sqlite")
    finally:
        F.MARGIN = saved
    on = sorted((b, s) for b, s in F._shadow(d / "s.sqlite").execute("SELECT b, stat FROM flags WHERE card=1"))
    assert on == [("Collin Gillespie", "pts"), ("Gui Santos", "pts"), ("Jamal Murray", "pts_ast")], on


def test_backfill_wowy_v0_shares_wowy_slots():
    d = pathlib.Path(tempfile.mkdtemp())
    sh = F._shadow(d / "s.sqlite")
    for fid, at, tier, b, pid, stat, line, m in (
            ("a", "2026-10-24T03:00:00", "wowy_v0", "VJ Edgecombe", 1, "pts", 12.5, 4.3),
            ("b", "2026-10-24T03:00:00", "wowy_v0", "VJ Edgecombe", 1, "pra", 21.5, 5.0),
            ("c", "2026-10-24T20:00:00", "wowy", "VJ Edgecombe", 1, "pts", 13.5, 3.7)):
        sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, team, b, stat, line, margin, pid) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?)", (fid, at, GD, tier, "PHI", b, stat, line, m, pid))
    sh.commit()
    saved, F.MARGIN = F.MARGIN, {"pra": 5.0, "pts": 3.0, "reb": 2.0}
    try:
        F.card_backfill([GD], path=d / "s.sqlite")
    finally:
        F.MARGIN = saved
    got = dict(F._shadow(d / "s.sqlite").execute("SELECT flag_id, card FROM flags"))
    assert got == {"a": 1, "b": 0, "c": 0}, got     # earliest pass first, its single lead; no NULL left


def test_board_shows_only_the_card():
    src = pathlib.Path(F.__file__).with_name("nba_board.py").read_text()
    assert "void_reason IS NULL AND COALESCE(card, 1) = 1" in src


def test_mutants():
    src = pathlib.Path(F.__file__).read_text()
    for tag, a, b in (
            ("no one-per-player", 'if sh.execute(f"SELECT 1 FROM flags WHERE game_date=? AND pid=? AND {CARD_ON} LIMIT 1", (gd, pid)).fetchone():\n        return 0',
             'if False:\n        return 0'),
            ("3 slots", "    if len(mates) >= 2:\n        return 0", "    if len(mates) >= 3:\n        return 0"),
            ("shared components allowed", "return 0 if any(comp & CARD_COMPONENTS.get(s, frozenset(s)) for _, s in mates) else 1",
             "return 1"),
            ("not sticky", "    if prev:\n        return prev[0]\n", ""),
            ("pings every flag", "        if cur.rowcount and card:\n", "        if cur.rowcount:\n"),
            ("excess order ignored", "0.0 if f[\"tier\"] == \"priced\" else -_excess(f)))", "0.0))"),
            ("best excess, not singles first", "key = (f[\"stat\"] in COMBO_STATS, -_excess(f))",
             "key = (False, -_excess(f))"),
            ("non-leads carded", "    if not lead:\n        return 0\n", "")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_flags_mut18.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_flags_mut18")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_flags_mut18", None)


if __name__ == "__main__":
    test_card(); test_backfill_matches_live(); test_board_shows_only_the_card(); test_mutants()
    print("test_nba_card: OK")


def test_mutants_22():
    src = pathlib.Path(F.__file__).read_text()
    for tag, a, b in (
            ("any line carded", "    if stale != \"STALE\":\n        return 0\n", ""),
            ("no minutes gate", "    if f[\"tier\"] == \"wowy\" and not (f.get(\"d_min\") is not None and DMIN_BAND[0] <= f[\"d_min\"] <= DMIN_BAND[1]):\n        return 0\n", ""),
            ("priced not sticky", "    if prev:\n        return prev[0]\n    if stale", "    if False:\n        return prev[0]\n    if stale")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_flags_mut22.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check22(importlib.import_module("nba_flags_mut22")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_flags_mut22", None)


def test_combo_decision():
    import nba_clv as V

    def rows(n, wins, stat="pra", at="2026-10-25T01:00:00", tier="wowy"):
        return [{"tier": tier, "stat": stat, "logged_at": at, "game_date": f"2026-11-{1 + i // 9:02d}",
                 "pid": i, "line": 20.5, "odds": 1.87, "actual": 25.0 if i < wins else 15.0} for i in range(n)]
    assert V.combo_decision(rows(59, 59))["verdict"] == "accumulating (59/60)"
    assert V.combo_decision(rows(60, 32))["verdict"] == "EXCLUDE combos from the card"   # 32*.87-28 = -0.16u
    assert V.combo_decision(rows(60, 33))["verdict"] == "REVERT the card to best excess"  # +1.71u
    noise = (rows(60, 0, stat="pts") + rows(60, 0, at="2026-10-24T20:00:00")       # singles, pre-cutover
             + rows(60, 0, tier="priced"))
    assert V.combo_decision(noise + rows(60, 33))["n"] == 60
    assert V.combo_decision(rows(60, 33) + rows(60, 33))["n"] == 60                 # one per play
