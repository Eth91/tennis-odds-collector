"""Amendment 33: nba_tracking.fetch rejects a date whose response cannot be one game per player, on a fake
feed (no network). Amendment 34: a date posted part way (a team that played has no rows) stays pending. The real bad dates: 2026-04-01 (517 potential assists in 18 min) and 2026-10-22 (Jokić 44
potential assists / 101 passes in 35 min). MUTANTS in test_mutants()."""
import importlib
import pathlib
import re
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_tracking as T

P_H = ["PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "GP", "MIN", "PASSES_MADE", "AST", "FT_AST", "SECONDARY_AST",
       "POTENTIAL_AST"]
R_H = ["PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "GP", "MIN", "REB", "OREB_CHANCES", "DREB_CHANCES", "REB_CHANCES"]


def resp(headers, rows, with_min=True):
    h = headers if with_min else [c for c in headers if c != "MIN"]
    return {"headers": h, "rowSet": [[r.get(c, 0) for c in h] for r in rows]}


def passing(rows, with_min=True):                  # (pid, min, passes, potential assists)
    return resp(P_H, [{"PLAYER_ID": p, "PLAYER_NAME": f"P{p}", "GP": 1, "MIN": m, "PASSES_MADE": ps,
                       "AST": 1, "POTENTIAL_AST": pa} for p, m, ps, pa in rows], with_min)


def rebounding(rows, with_min=True):               # (pid, min, rebound chances)
    return resp(R_H, [{"PLAYER_ID": p, "PLAYER_NAME": f"P{p}", "GP": 1, "MIN": m, "REB": 1,
                       "REB_CHANCES": rc} for p, m, rc in rows], with_min)


FEED = {   # date -> (Passing, Rebounding)
    # good: 38 potential assists in 38 min and 21 chances in 15 min sit ON the caps (only beyond is rejected);
    # 1 minute with 3 potential assists / 2 chances is a garbage-time stint, judged on the 10-minute floor
    "2026-10-23": (passing([(1, 38.0, 90, 38), (2, 1.0, 2, 3)]),
                   rebounding([(1, 38.0, 15), (2, 1.0, 2), (3, 15.0, 21)])),
    "2026-10-22": (passing([(1, 35.0, 101, 44)]), rebounding([(1, 35.0, 18)])),     # Jokić: Passing bad only
    "2026-04-01": (passing([(1, 18.0, 68, 517)]), rebounding([(1, 18.0, 8)])),      # multi-game totals
    "2026-10-24": (passing([(1, 30.0, 60, 10)]), rebounding([(1, 30.0, 43)])),      # Rebounding bad only
    # no MIN column: absolute caps, 40 potential assists / 150 passes
    "2025-11-01": (passing([(1, None, 150, 40)], False), rebounding([(1, None, 60)], False)),
    "2025-11-02": (passing([(1, None, 151, 20)], False), rebounding([(1, None, 10)], False)),
    "2025-11-03": (passing([(1, None, 90, 41)], False), rebounding([(1, None, 10)], False)),
}
GOOD, BAD = ["2025-11-01", "2026-10-23"], ["2025-11-02", "2025-11-03", "2026-04-01", "2026-10-22", "2026-10-24"]


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    calls = []

    def fake_get(url, tries=4):
        mm, dd, yy = re.search(r"DateFrom=(\d\d)/(\d\d)/(\d{4})", url).groups()
        d, measure = f"{yy}-{mm}-{dd}", re.search(r"PtMeasureType=(\w+)", url).group(1)
        calls.append((d, measure, re.search(r"Season=([\d-]+)", url).group(1)))
        return FEED[d][0 if measure == "Passing" else 1]
    mod._get, mod.PAUSE_S = fake_get, 0
    mod.DB = pathlib.Path(tempfile.mkdtemp()) / "t.sqlite"
    mod.BOXES = mod.DB.parent / "no_boxes.json"                 # amendment 34's guard has nothing to compare
    rejected = mod.fetch([], dates=sorted(FEED))
    want(rejected == BAD, f"rejected {rejected} == {BAD}")
    con = sqlite3.connect(mod.DB)
    stored = {d for (d,) in con.execute("SELECT DISTINCT date FROM tracking")}
    marked = {d for (d,) in con.execute("SELECT date FROM fetched GROUP BY date HAVING COUNT(*) = 2")}
    want(stored == marked == set(GOOD), f"good dates stored and marked done: {sorted(stored)}, {sorted(marked)}")
    want(con.execute("SELECT COUNT(*) FROM fetched WHERE date IN (%s)" % ",".join("?" * len(BAD)), BAD).fetchone()[0] == 0,
         "a rejected date stores nothing for EITHER measure (a missing measure would read as 0)")
    want(con.execute("SELECT potential_ast, reb_chances FROM tracking WHERE date='2026-10-23' AND player_id=2").fetchone()
         == (3.0, 2.0), "the garbage-time stint is stored as fetched")
    want(("2026-04-01", "Passing", "2025-26") in calls and ("2026-10-22", "Passing", "2026-27") in calls,
         "--dates asks for each date's own season")
    con.close()
    calls.clear()
    want(mod.fetch([], dates=sorted(FEED)) == BAD and sorted({c[0] for c in calls}) == BAD,
         "rejected dates stay pending: the next run retries them, and only them")
    return ok


def test_guard():
    assert check(T)


def check_complete(mod):
    """10-26: AAA (players 1, 2) and BBB (3) played. The league first posts AAA only, then both. 10-27 is not in the
    box cache, so there is nothing to compare and it is stored as fetched."""
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    import json
    tmp = pathlib.Path(tempfile.mkdtemp())
    (tmp / "boxes.json").write_text(json.dumps({"g1": {"date": "2026-10-26", "players": [
        {"pid": 1, "team": "AAA"}, {"pid": 2, "team": "AAA"}, {"pid": 3, "team": "BBB"}]}}))
    part = {"2026-10-26": (passing([(1, 30.0, 40, 8), (2, 20.0, 20, 3)]), rebounding([(1, 30.0, 9), (2, 20.0, 4)])),
            "2026-10-27": (passing([(5, 30.0, 40, 8)]), rebounding([(5, 30.0, 9)]))}
    full = dict(part, **{"2026-10-26": (passing([(1, 30.0, 40, 8), (2, 20.0, 20, 3), (3, 25.0, 30, 5)]),
                                        rebounding([(1, 30.0, 9), (2, 20.0, 4), (3, 25.0, 11)]))})
    feed = part

    def fake_get(url, tries=4):
        mm, dd, yy = re.search(r"DateFrom=(\d\d)/(\d\d)/(\d{4})", url).groups()
        return feed[f"{yy}-{mm}-{dd}"][0 if "PtMeasureType=Passing" in url else 1]
    mod._get, mod.PAUSE_S, mod.DB, mod.BOXES = fake_get, 0, tmp / "t.sqlite", tmp / "boxes.json"
    want(mod.fetch([], dates=sorted(part)) == [], "a date posted part way is not a rejection")
    con = sqlite3.connect(mod.DB)
    done = lambda: {d for (d,) in con.execute("SELECT date FROM fetched GROUP BY date HAVING COUNT(*) = 2")}
    rows = lambda d: con.execute("SELECT COUNT(*) FROM tracking WHERE date = ?", (d,)).fetchone()[0]
    want(done() == {"2026-10-27"} and rows("2026-10-26") == 0, "AAA only: nothing stored for 10-26, it stays pending")
    feed = full
    mod.fetch([], dates=sorted(part))
    want(done() == {"2026-10-26", "2026-10-27"} and rows("2026-10-26") == 3, "both teams posted: stored on the next run")
    con.close()
    return ok


def test_complete():
    assert check_complete(T)


def test_complete_mutants():
    for name, a, b in (("guard off", "        if short:", "        if False:"),
                       ("any rows count as complete", "return sorted(t for t, pids in teams.items() if not pids & ids)",
                        "return sorted(teams) if not ids else []")):
        src = pathlib.Path(T.__file__).read_text()
        assert src.count(a) == 1, name
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_tracking_mut34.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({name}) — must fail:")
            assert not check_complete(importlib.import_module("nba_tracking_mut34")), name
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_tracking_mut34", None)


def test_mutants():
    for name, a, b in (
            ("no minutes floor", 'm = max(r[ix["MIN"]] or 0.0, MIN_FLOOR)', 'm = r[ix["MIN"]] or 1e-9'),
            ("cap inclusive", "if c in ix and (r[ix[c]] or 0) / m > cap:", "if c in ix and (r[ix[c]] or 0) / m >= cap:"),
            ("guard off", "        if bad:\n", "        if False:\n"),
            ("bad measure dropped, the other stored",
             "        bad = [(m, w) for m, rs in got.items() if (w := implausible(rs))]\n",
             "        got = {m: rs for m, rs in got.items() if not implausible(rs)}\n        bad = []\n"),
            ("no fallback without MIN", "for c, cap in CAP_ABS.items():", "for c, cap in ():")):
        src = pathlib.Path(T.__file__).read_text()
        assert src.count(a) == 1, name
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_tracking_mut33.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            m = importlib.import_module("nba_tracking_mut33")
            print(f"MUTANT ({name}) — must fail:")
            assert not check(m), name
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_tracking_mut33", None)


if __name__ == "__main__":
    test_guard()
    test_mutants()
    test_complete()
    test_complete_mutants()
    print("test_nba_tracking: OK")
