"""NBA_SXS_PREREG.md: the replay tool and the side-by-side rules on one synthetic day. Observations (a targeted poll
sees only the games it wrote), the news rules' stale check and window, the tip - 30 rules, grading (alternate
de-vig at the close, voids), no look-ahead, the registry and the verdicts. MUTANTS in test_mutants()."""
import importlib
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_replay as RP
import nba_sxs as S
import nba_sxs_rules as SR

D, G, TIP = "2026-11-01", "G1", "2026-11-02T00:00:00Z"        # 8 pm ET on the date
X, B, C, O, E = 1, 2, 3, 4, 5                                  # X absent (HOM), B and C his teammates, O opponent, E bench (Out)


def stores(tmp, fd_after_report="2026-11-01T17:00:30"):
    p = {k: tmp / f"{k}.sqlite" for k in ("lines", "news", "matchup", "gamelogs", "shadow", "proj_log")}
    q = sqlite3.connect(p["lines"])
    q.execute("CREATE TABLE quotes (seen_at, book, gid, tip_utc, pid, player, stat, line, side, odds)")
    q.execute("CREATE TABLE cycles (ts, book, status, rows, events, matched_events, resolved, unresolved, detail)")
    quotes = []

    def board(ts, book, pid, line, o, u, stat="points"):
        quotes.extend([(ts, book, G, TIP, pid, "", stat, line, "over", o), (ts, book, G, TIP, pid, "", stat, line, "under", u)])
    board("2026-11-01T15:00:00", "fd", B, 10.5, 1.9, 1.9)
    board("2026-11-01T15:00:00", "fd", C, 12.5, 1.9, 1.9)
    board("2026-11-01T15:00:00", "fd", O, 8.5, 1.9, 1.9)
    board("2026-11-01T15:00:00", "fd", E, 3.5, 1.9, 1.9)
    board("2026-11-01T15:00:30", "dk", E, 3.5, 1.91, 1.89)
    board("2026-11-01T15:00:30", "dk", B, 10.5, 1.91, 1.89)
    board("2026-11-01T15:00:30", "dk", C, 12.5, 1.91, 1.89)
    quotes += [(fd_after_report, "fd", G, TIP, C, "", "points", 12.5, s, None) for s in ("over", "under")]
    board(fd_after_report, "fd", C, 13.5, 1.9, 1.9)                       # C's FanDuel line moves on the news; B's doesn't
    board("2026-11-01T23:20:00", "fd", B, 11.5, 1.85, 1.95)
    quotes += [("2026-11-01T23:20:00", "fd", G, TIP, B, "", "points", 10.5, s, o) for s, o in (("over", 1.70), ("under", None))]
    board("2026-11-01T23:25:00", "dk", B, 11.5, 2.10, 1.75)
    q.executemany("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)", quotes)
    cyc = [("2026-11-01T15:00:00", "fd", "ok"), ("2026-11-01T15:00:30", "dk", "ok"), ("2026-11-01T16:10:00", "fd", "ok"),
           ("2026-11-01T17:00:10", "fd", "game"),                       # targeted poll of another game: wrote nothing for G1
           (fd_after_report, "fd", "ok"), ("2026-11-01T17:05:00", "dk", "ok"), ("2026-11-01T23:20:00", "fd", "ok"),
           ("2026-11-01T23:25:00", "dk", "ok"), ("2026-11-01T23:40:00", "fd", "ok"), ("2026-11-02T00:01:00", "fd", "ok")]
    q.executemany("INSERT INTO cycles (ts, book, status) VALUES (?,?,?)", cyc)
    q.commit()
    n = sqlite3.connect(p["news"])
    n.execute("CREATE TABLE snapshots (mark, published_at, game_date, matchup, team, pid, player, status, reason)")
    n.executemany("INSERT INTO snapshots (published_at, game_date, team, pid, status) VALUES (?,?,?,?,?)",
                  [("2026-11-01T16:00:04+00:00", D, "HOM", X, "Questionable"),
                   ("2026-11-01T17:00:04+00:00", D, "HOM", X, "Out"),
                   ("2026-11-01T17:00:04+00:00", D, "HOM", E, "Out")])          # E (not a regular) is out too: no signal for him
    n.commit()
    m = sqlite3.connect(p["matchup"])
    m.execute("CREATE TABLE games (gid, season, date, home, away, home_pts, away_pts)")
    m.execute("CREATE TABLE player_games (gid, team, pid, pos, starter, min, pts, reb, ast, fg3m, stl, blk, tov, fga, fg3a, fta)")
    m.execute("INSERT INTO games VALUES (?, '2026-27', ?, 'HOM', 'AWY', 100, 99)", (G, D))
    m.executemany("INSERT INTO player_games (gid, team, pid, min, pts, reb, ast, fg3m) VALUES (?,?,?,?,?,?,?,?)",
                  [(G, "HOM", B, 30, 12, 4, 3, 1), (G, "HOM", C, 28, 10, 5, 2, 0), (G, "AWY", O, 0, 0, 0, 0, 0)])
    m.commit()
    g = sqlite3.connect(p["gamelogs"])
    g.execute("CREATE TABLE logs (season, game_id, date, team, player_id, player, min, pts, reb, ast, fg3m)")
    g.executemany("INSERT INTO logs VALUES ('2026-27', ?, ?, ?, ?, '', ?, 10, 4, 3, 1)",
                  [(f"g{i}", f"2026-10-{10 + i:02d}", tm, pid, mn) for i in range(10)
                   for pid, tm, mn in ((X, "HOM", 30.0), (B, "HOM", 25.0), (C, "HOM", 22.0), (O, "AWY", 20.0), (E, "HOM", 10.0))])
    g.commit()
    return p


def isolate(mod_sr, tmp):
    """Point every store the rules read at the test's folder (absent files read as empty) and drop their caches, so a
    checkout with real data files next to the code can't leak into the replay."""
    for name in ("MATCHUP_DB", "LINEUPS_DB", "INDEX_JSON", "ROLE_GAMELOGS_DB", "TRACKING_DB", "NEWS_DB"):
        if hasattr(mod_sr, name):
            setattr(mod_sr, name, tmp / f"absent_{name.lower()}")
    for cache in ("_VD", "_RD", "_RT", "_DV", "_FD", "_ED"):
        getattr(mod_sr, cache, {}).clear()


def replay(mod_rp=RP, mod_sr=SR, **kw):
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = stores(tmp, **kw)
    isolate(mod_sr, tmp)
    day = mod_rp.Day(D, p["lines"], p["news"], p["matchup"], mod_rp.History(p["gamelogs"], p["matchup"]))
    rules = [cls() for cls in mod_sr.RULES if cls.kind == "replay"]
    sig = mod_rp.run_day(day, rules)
    for s in sig:
        s["date"] = D
    return mod_rp.grade(day, sig, mod_rp.box_of(p["matchup"], list(day.games))), p


def pick(sig, rule):
    return sorted((s["pid"], s["market"], s["side"], s["line"], s["book"], s["odds"]) for s in sig if s["rule"] == rule)


def check(mod_rp=RP, mod_sr=SR):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    sig, p = replay(mod_rp, mod_sr)
    want(all(a[0] < D for a in mod_rp.History(p["gamelogs"], p["matchup"]).before(B, D)),
         "the history a rule reads stops before the date (no same-day box scores)")
    want(pick(sig, "NEWS_FD") == [(B, "points", "over", 10.5, "fd", 1.9)],
         "NEWS_FD: B's unchanged FanDuel over after X goes Out; C's moved line is not stale; the targeted poll is not an observation")
    want(pick(sig, "NEWS_DK") == [(B, "points", "over", 10.5, "dk", 1.91), (C, "points", "over", 12.5, "dk", 1.91)],
         "NEWS_DK: DraftKings unchanged for both at its first observation")
    want(pick(sig, "NULL_TIP30") == [(B, "points", "over", 11.5, "fd", 1.85), (C, "points", "over", 13.5, "fd", 1.9),
                                     (O, "points", "over", 8.5, "fd", 1.9), (E, "points", "over", 3.5, "fd", 1.9)],
         "NULL_TIP30: FanDuel's main overs at tip - 30")
    t4 = [s for s in sig if s["rule"] == "T4_TIP30"]
    want(pick(sig, "T4_TIP30") == [(B, "points", "over", 11.5, "dk", 2.10)] and t4[0]["t"] == "2026-11-01T23:30:00",
         "T4_TIP30: DraftKings 2.10 vs FanDuel's fair, at tip - 30")
    lag = [s for s in sig if s["rule"] == "DK_LAGS_FD"]
    want([(s["pid"], s["side"], s["line"], s["t"]) for s in lag] == [(B, "over", 11.5, "2026-11-01T23:40:00")],
         "DK_LAGS_FD: at the next FanDuel observation after DraftKings' stale price")
    fd = next((s for s in sig if s["rule"] == "NEWS_FD"), {})
    want(fd.get("result") == "win" and abs((fd.get("q_close") or 0) - (1 / 1.70) / (1 / 1.85 + 1 / 1.95)) < 1e-9
         and abs((fd.get("clv") or 0) - (fd["q_close"] * 1.9 - 1)) < 1e-9,
         "grading: win; CLV from FanDuel's over-only 10.5 alternate de-vigged at the main rung's overround")
    nul = {s["pid"]: s for s in sig if s["rule"] == "NULL_TIP30"}
    want(nul[O]["result"] == "void" and nul[O]["profit"] is None and nul[E]["result"] == "void" and nul[C]["result"] == "loss",
         "a DNP (0 minutes, or no box row) is void; C's 10 under 13.5 loses")
    late, _ = replay(mod_rp, mod_sr, fd_after_report="2026-11-01T17:10:30")
    want(pick(late, "NEWS_FD") == [], "no FanDuel observation within 10 minutes of the report: no signal")
    return ok


def test_replay_rules():
    assert check()


def test_no_lookahead():
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = stores(tmp)
    h = RP.History(p["gamelogs"], p["matchup"])
    assert all(d < D for d, *_ in h.before(B, D))                         # the day's own box score is excluded
    v = RP.View(RP.Day(D, p["lines"], p["news"], p["matchup"], h))
    assert v.last10_min(B) == (25.0, 10) and not hasattr(v, "box")
    sig, p2 = replay()
    sqlite3.connect(p2["matchup"]).execute("DELETE FROM player_games").connection.commit()
    isolate(SR, p2["matchup"].parent)
    day = RP.Day(D, p2["lines"], p2["news"], p2["matchup"], RP.History(p2["gamelogs"], p2["matchup"]))
    again = RP.run_day(day, [cls() for cls in SR.RULES if cls.kind == "replay"])
    assert sorted((s["rule"], s["pid"], s["market"], s["side"], s["t"]) for s in again) == \
        sorted((s["rule"], s["pid"], s["market"], s["side"], s["t"]) for s in sig)     # signals never read results


def test_q_close():
    assert RP.q_close({(10.5, "over"): 1.9, (10.5, "under"): 1.9}, "under", 10.5) == 0.5
    alt = {(11.5, "over"): 2.0, (11.5, "under"): 1.8, (10.5, "over"): 1.6}
    assert abs(RP.q_close(alt, "under", 10.5) - (1 - (1 / 1.6) / (1 / 2.0 + 1 / 1.8))) < 1e-12
    assert RP.q_close(alt, "over", 9.5) is None and RP.q_close({}, "over", 9.5) is None


def test_registry_matches():
    for cls in SR.RULES:
        at, fp = SR.REGISTRY[cls.name]
        assert fp == SR.fingerprint(cls), f"{cls.name} changed without a new registration"
        assert at >= SR.REGISTERED_AT[:10]


def test_phase_and_verdict():
    n = SR.RULES[0].name
    at, fp = SR.REGISTRY[n]
    assert S.phase(n, fp, at) == "forward" and S.phase(n, fp, "2026-10-23T00:00:00") == "development"
    assert S.phase(n, "deadbeef00", at) == "unregistered"
    clv = lambda m, lo, hi, k, dates: {"clv": {"n": k, "mean": m, "lo": lo, "hi": hi, "dates": dates}}
    assert S.verdict(clv(0.03, 0.01, 0.05, 199, 30), None).startswith("accumulating (199/200")
    assert S.verdict(clv(0.03, 0.01, 0.05, 400, 9), None).startswith("accumulating")          # too few dates
    assert S.verdict(clv(0.03, 0.01, 0.05, 400, 10), None) == "BEATS THE CLOSE"
    assert S.verdict(clv(-0.03, -0.05, -0.01, 400, 10), None) == "LOSES TO THE CLOSE"
    assert S.verdict(clv(0.01, -0.01, 0.03, 400, 10), None) == "NO EDGE SHOWN"
    assert S.verdict(clv(0.03, 0.01, 0.05, 400, 10), False).startswith("GRADER CHECK FAILED")
    roi = dict(clv(0.03, 0.01, 0.05, 600, 25), roi={"n": 600, "lo": 0.01, "dates": 25})
    assert S.verdict(roi, None) == "BEATS THE CLOSE; PROFITABLE"


def test_mutants():
    rp_src = pathlib.Path(RP.__file__).read_text()
    sr_src = pathlib.Path(SR.__file__).read_text()
    for target, tag, a, b in (
            ("rp", "a targeted poll sees every game", "(wrote.get((book, ts), set()) if status == \"game\" else set())",
             "(set(gids) if status == \"game\" else set())"),
            ("rp", "same-day box scores leak into history", "if a[0] < date]", "if a[0] <= date]"),
            ("rp", "alternate de-vig dropped", "        p = (1 / o) / (1 / m[1] + 1 / m[2])\n", "        return None\n"),
            ("rp", "reports applied after the rules run", "            for tm, pid, st in payload:\n                day.status[pid] = st\n        for r in rules:",
             "        for r in rules:"),
            ("sr", "stale check dropped", "if m and m[0] == line and m[1] == over:", "if m:"),
            ("sr", "window ignored", "            if RP.minus(v.t, self.window) > P:\n                continue                                 # no observation",
             "            if False:\n                continue                                 # no observation"),
            ("sr", "T4 at tip - 5", "        if minutes != 30:\n            return ()\n        return [s for", "        if minutes != 5:\n            return ()\n        return [s for")):
        src = rp_src if target == "rp" else sr_src
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        if target == "rp":
            (d / "nba_replay_mut.py").write_text(src.replace(a, b))
            (d / "nba_sxs_rules_mut.py").write_text(sr_src.replace("import nba_replay as RP", "import nba_replay_mut as RP"))
        else:
            (d / "nba_replay_mut.py").write_text(rp_src)
            (d / "nba_sxs_rules_mut.py").write_text(src.replace(a, b).replace("import nba_replay as RP", "import nba_replay_mut as RP"))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_replay_mut"), importlib.import_module("nba_sxs_rules_mut")), tag
        finally:
            sys.path.remove(str(d))
            for k in ("nba_replay_mut", "nba_sxs_rules_mut"):
                sys.modules.pop(k, None)


def test_q15_a_failing_game_is_skipped_not_raised(capsys):
    """Amendment 11: an error in Q15_LR10 on one game is logged and skips that game; the other rules keep running."""
    class Boom(SR.Q15_LR10):
        def judge_game(self, v, gid):
            raise ValueError("boom")

    v = type("V", (), {"date": "2026-11-01"})()
    assert Boom().on_tick(v, "g1", 30) == () and Boom().on_tick(v, "g1", 60) == ()
    assert "boom" in capsys.readouterr().err
