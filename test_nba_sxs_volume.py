"""NBA_SXS_PREREG.md amendment 1: the volume rules on the side-by-side's synthetic day. X (a C) goes Out; B (a C, fewer
minutes) is the next man up and a new starter; C (a usual starter) is Active but out of the starting five; a lineup
snapshot fetched after tip - 30 must not be read. MUTANTS in test_mutants()."""
import importlib
import json
import pathlib
import sqlite3
import sys
import tempfile
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_replay as RP
import nba_sxs_rules as SR
import test_nba_sxs as T

D = T.D


def lineup(starters_home, active_home, starters_away):
    pl = lambda ids, act: [{"personId": i, "position": "G" if i in ids else "", "lineupStatus": "Confirmed",
                            "rosterStatus": "Active" if i in act else "Inactive"} for i in sorted(act | ids)]
    return zlib.compress(json.dumps({"games": [{"gameId": T.G, "homeTeam": {"teamAbbreviation": "HOM", "players": pl(starters_home, active_home)},
                                                "awayTeam": {"teamAbbreviation": "AWY", "players": pl(starters_away, starters_away)}}]}).encode())


def stores(tmp):
    p = T.stores(tmp)
    m = sqlite3.connect(p["matchup"])                      # 10 earlier games: X and C start, B comes off the bench
    for i in range(10):
        g, d = f"H{i}", f"2026-10-{21 + i:02d}"
        m.execute("INSERT INTO games VALUES (?, '2026-27', ?, 'HOM', 'AWY', 100, 99)", (g, d))
        m.executemany("INSERT INTO player_games (gid, team, pid, starter, min, pts, reb, ast, fg3m) VALUES (?,?,?,?,?,?,?,?,?)",
                      [(g, "HOM", T.X, 1, 30, 20, 8, 2, 0), (g, "HOM", T.B, 0, 20, 10, 6, 1, 0), (g, "HOM", T.C, 1, 25, 12, 4, 3, 1),
                       (g, "AWY", T.O, 1, 30, 15, 3, 4, 2)])           # C (an F) has more minutes than B; O always starts
    m.commit()
    p["index"] = tmp / "index.json"
    p["index"].write_text(json.dumps({"players": {str(T.X): ["HOM", "X", "C"], str(T.B): ["HOM", "B", "C-F"],
                                                  str(T.C): ["HOM", "C", "F"], str(T.E): ["HOM", "E", "C"],
                                                  str(T.O): ["AWY", "O", "G"]}}))
    p["lineups"] = tmp / "lineups.sqlite"
    lc = sqlite3.connect(p["lineups"])
    lc.execute("CREATE TABLE snaps (fetched_at TEXT, date_et TEXT, sha TEXT, body BLOB)")
    five = {T.B, 11, 12, 13, 14}
    lc.execute("INSERT INTO snaps VALUES (?, ?, 'a', ?)", ("2026-11-01T23:20:00+00:00", D, lineup(five, five | {T.C, 15}, {T.O, 21, 22, 23, 24})))
    late = {T.C, 11, 12, 13, 14}                                 # after tip - 30: C back in; must not be read at 23:30
    lc.execute("INSERT INTO snaps VALUES (?, ?, 'b', ?)", ("2026-11-01T23:35:00+00:00", D, lineup(late, late | {T.B, 15}, {T.O, 21, 22, 23, 24})))
    lc.commit()
    return p


def check(mod_sr=SR):
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = stores(tmp)
    mod_sr.LINEUPS_DB, mod_sr.MATCHUP_DB, mod_sr.INDEX_JSON = p["lineups"], p["matchup"], p["index"]
    mod_sr._VD.clear()
    day = RP.Day(D, p["lines"], p["news"], p["matchup"], RP.History(p["gamelogs"], p["matchup"]))
    vol = [c() for c in mod_sr.RULES if c.name in ("DEPTH_NEXT", "DEPTH_NEXT_TIP30", "NEW_STARTER", "LOST_START")]
    sig = RP.run_day(day, vol)
    got = lambda r: sorted((s["pid"], s["market"], s["side"], s["line"], s["odds"], s["t"]) for s in sig if s["rule"] == r)
    ok = got("DEPTH_NEXT") == [(T.B, "points", "over", 10.5, 1.9, "2026-11-01T17:00:30")]        # B behind X (both C), E is Out
    ok &= got("DEPTH_NEXT_TIP30") == [(T.B, "points", "over", 11.5, 1.85, "2026-11-01T23:30:00")]
    ok &= got("NEW_STARTER") == [(T.B, "points", "over", 11.5, 1.85, "2026-11-01T23:30:00")]       # started 0 of 10
    ok &= got("LOST_START") == [(T.C, "points", "under", 13.5, 1.9, "2026-11-01T23:30:00")]       # started 10 of 10, Active
    return bool(ok)


def test_volume_rules():
    try:
        assert check()
    finally:
        SR._VD.clear()


def test_registry_covers_volume_rules():
    for name in ("DEPTH_NEXT", "DEPTH_NEXT_TIP30", "NEW_STARTER", "LOST_START"):
        cls = next(c for c in SR.RULES if c.name == name)
        assert SR.REGISTRY[name][1] == SR.fingerprint(cls) and cls.deps == SR.VOL_DEPS


def test_mutants():
    src = pathlib.Path(SR.__file__).read_text()
    for tag, a, b in (("lineup look-ahead", "            if f <= t:\n                best = teams", "            best = teams"),
                      ("next man ignores position", " or vd.group(p) != gx:", ":"),
                      ("new starter threshold", "if n >= 3 and st <= 0.3 * n:", "if n >= 3 and st <= n:"),
                      ("lost start ignores the starters", "for p in sorted(e[\"active\"] - e[\"starters\"]):", "for p in sorted(e[\"active\"]):")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_sxs_rules_vmut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            assert not check(importlib.import_module("nba_sxs_rules_vmut")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_sxs_rules_vmut", None)
