"""NBA_INJURY_REACTION_PREREG.md guards for nba_injury_reaction.py, on a hand-built fixture: a fresh Out is new against
the previous report listing his game; he must have played his team's last game, average 15+ minutes over 2+ games and
tip 30+ minutes after the report; news counts only before the report; the baseline is the last observation at or
before the report (within 30 min); stale means same line and under 3.0 no-vig points; latency is [L, U]; DraftKings
lags only after FanDuel's move, valued on the side FanDuel moved toward; opponents are never teammates; control teams
had no fresh Out. MUTANTS in test_mutants()."""
import datetime as dt
import importlib
import math
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_injury_reaction as M

TIP = "2026-10-28T00:00:00Z"        # the AAA-BBB game
EARLY = "2026-10-27T19:30:00Z"      # the CCC-DDD game: 15 min after report 2


def utc(hms):
    return dt.datetime.fromisoformat(f"2026-10-27T{hms}+00:00")


def fixture():
    d = pathlib.Path(tempfile.mkdtemp())
    lines = sqlite3.connect(d / "l.sqlite")
    lines.execute("CREATE TABLE cycles (ts, book, status, rows, events, matched_events, resolved, unresolved, detail)")
    lines.execute("CREATE TABLE quotes (seen_at, book, gid, tip_utc, pid, player, stat, line, side, odds)")
    for book, times in (("fd", ("19:14:00", "19:17:00", "19:20:00", "19:40:00", "23:50:00")),
                        ("dk", ("19:15:00", "19:18:00", "19:31:00", "23:45:00"))):
        lines.executemany("INSERT INTO cycles (ts, book, status) VALUES (?, ?, 'ok')", [(f"2026-10-27T{t}", book) for t in times])
    q = [  # (time, book, gid, tip, pid, stat, line, over, under)
        ("19:14:00", "fd", "G3", TIP, 2, "points", 14.5, 1.87, 1.87),
        ("19:14:00", "fd", "G3", TIP, 2, "rebounds", 5.5, 1.87, 1.87),
        ("19:14:00", "fd", "G3", TIP, 2, "assists", 3.5, 1.87, 1.87),
        ("19:14:00", "fd", "G3", TIP, 3, "points", 20.5, 1.87, 1.87),
        ("19:14:00", "fd", "C2", EARLY, 6, "points", 10.5, 1.87, 1.87),
        ("19:17:00", "fd", "G3", TIP, 2, "rebounds", 5.5, 1.80, 1.95),   # 2.0 no-vig points: still stale
        ("19:20:00", "fd", "G3", TIP, 2, "points", 14.5, 1.70, 2.15),   # FanDuel moves up a point
        ("19:20:00", "fd", "G3", TIP, 2, "points", 15.5, 1.87, 1.87),
        ("19:40:00", "fd", "G3", TIP, 2, "assists", 3.5, 1.65, 2.25),   # same line, 7.7 no-vig points: moved
        ("19:15:00", "dk", "G3", TIP, 2, "points", 14.5, 1.87, 1.87),
        ("19:15:00", "dk", "G3", TIP, 3, "points", 20.5, 1.87, 1.87),
        ("23:45:00", "dk", "G3", TIP, 2, "points", 14.5, None, None),   # DraftKings catches up late
        ("23:45:00", "dk", "G3", TIP, 2, "points", 15.5, 1.87, 1.87)]
    for t, book, gid, tip, pid, stat, line, o, u in q:
        lines.executemany("INSERT INTO quotes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          [(f"2026-10-27T{t}", book, gid, tip, pid, f"P{pid}", stat, line, side, odds)
                           for side, odds in (("over", o), ("under", u))])
    lines.commit()
    news = sqlite3.connect(d / "n.sqlite")
    news.execute("CREATE TABLE reports (mark, url, published_at, fetched_at, n_rows, n_matchups, unresolved, missing_teams)")
    news.execute("CREATE TABLE snapshots (mark, published_at, game_date, matchup, team, pid, player, status, reason)")
    news.execute("CREATE TABLE news_items (source, item_id, detected_at, player, pid, team, game_date, status, headline, body, "
                 "provenance, seeded)")
    r1, r2 = ("2026-10-27T15:00", "2026-10-27T19:00:04+00:00"), ("2026-10-27T15:15", "2026-10-27T19:15:04+00:00")
    news.executemany("INSERT INTO reports (mark, published_at) VALUES (?, ?)", [r1, r2])
    snaps = [(r1, "AAA", 1, "Questionable"), (r1, "AAA", 4, "Out"),
             (r2, "AAA", 1, "Out"), (r2, "AAA", 4, "Out"), (r2, "CCC", 5, "Out")]
    news.executemany("INSERT INTO snapshots (mark, published_at, game_date, team, pid, player, status) VALUES "
                     "(?, ?, '2026-10-27', ?, ?, ?, ?)", [(r[0], r[1], tm, pid, f"P{pid}", s) for r, tm, pid, s in snaps])
    news.execute("INSERT INTO news_items (source, detected_at, pid, game_date, status) VALUES "
                 "('x', '2026-10-27T19:20:00+00:00', 1, '2026-10-27', 'out')")      # after the report: not first
    news.commit()
    mu = sqlite3.connect(d / "m.sqlite")
    mu.execute("CREATE TABLE games (gid, season, date, home, away, home_pts, away_pts)")
    mu.execute("CREATE TABLE player_games (gid, team, pid, min)")
    games = [("G0", "2026-10-21", "AAA", "BBB"), ("G1", "2026-10-23", "AAA", "BBB"), ("G2", "2026-10-25", "AAA", "BBB"),
             ("G3", "2026-10-27", "AAA", "BBB"), ("C0", "2026-10-23", "CCC", "DDD"), ("C1", "2026-10-25", "CCC", "DDD"),
             ("C2", "2026-10-27", "CCC", "DDD")]
    mu.executemany("INSERT INTO games (gid, season, date, home, away) VALUES (?, '2026-27', ?, ?, ?)", games)
    pg = [(g, "AAA", 1, 30.0) for g in ("G0", "G1", "G2")] + [(g, "AAA", 4, 20.0) for g in ("G0", "G1")] \
        + [(g, "AAA", 2, 25.0) for g in ("G0", "G1", "G2")] + [(g, "BBB", 3, 30.0) for g in ("G0", "G1", "G2")] \
        + [(g, "CCC", 5, 30.0) for g in ("C0", "C1")] + [(g, "DDD", 6, 20.0) for g in ("C0", "C1")]
    mu.executemany("INSERT INTO player_games VALUES (?, ?, ?, ?)", pg)
    mu.commit()
    for c in (lines, news, mu):
        c.close()
    return d / "l.sqlite", d / "n.sqlite", d / "m.sqlite"


def run(mod):
    l, n, m = fixture()
    b = mod.Boards(l)
    ev, fresh, ft, team_of = mod.load_events(n, m, b)
    us, _ = mod.units(ev, b, team_of)
    return b, ev, fresh, ft, team_of, us


def unit(us, book, pid, stat):
    return next(u for u in us if u["book"] == book and u["pid"] == pid and u["stat"] == stat)


def check_events(mod=M):
    b, ev, fresh, *_ = run(mod)
    ok = len(fresh) == 3                                                 # P4 (r1), P1 (r2), P5 (r2); P4 not again in r2
    why = {f["pid"]: f["why_not"] for f in fresh}
    ok &= why[1] is None and why[4] is not None and why[5] is not None   # P4 missed the last game; P5 tips too soon
    ok &= len(ev) == 1 and [f["pid"] for f in ev[0]["outs"]] == [1] and ev[0]["prior"] == "Questionable"
    ok &= ev[0]["news_first"] is False                                   # news after the report is not first
    return bool(ok)


def check_track(mod=M):
    b, ev, fresh, ft, team_of, us = run(mod)
    ok = sorted((u["book"], u["pid"], u["stat"]) for u in us) == [("dk", 2, "points"), ("fd", 2, "assists"),
                                                                    ("fd", 2, "points"), ("fd", 2, "rebounds")]
    fp, fr, fa, dp = unit(us, "fd", 2, "points"), unit(us, "fd", 2, "rebounds"), unit(us, "fd", 2, "assists"), unit(us, "dk", 2, "points")
    ok &= fp["base_t"] == utc("19:14:00") and fp["base"][0] == 14.5      # the last check at or before the report
    ok &= fp["U"] == utc("19:20:00") and fp["L"] == utc("19:17:00") and fp["close_kind"] == "moved" and fp["close"][0] == 15.5
    ok &= [mod.stale_at(fp, t) for t in (1, 5, 15)] == ["stale", "moved", "moved"]
    ok &= fr["close_kind"] == "stale" and fr["U"] is None               # price jitter under 3.0 points
    ok &= fa["close_kind"] == "moved" and fa["U"] == utc("19:40:00")     # same line, price moved 3.0+ points
    ok &= dp["base_t"] == utc("19:15:00") and dp["L"] == utc("19:31:00") and dp["U"] == utc("23:45:00")
    ok &= [mod.stale_at(dp, t) for t in (1, 5, 15)] == ["stale", "stale", "stale"]
    pub = ev[0]["pub"]
    ok &= mod.track(b, "fd", "G3", 2, "points", pub.replace(hour=23, minute=30)) is None   # baseline 3.8 h old
    return bool(ok)


def check_lag(mod=M):
    b, ev, fresh, ft, team_of, us = run(mod)
    rows = mod.dk_lag(us, b)
    ok = len(rows) == 1 and rows[0]["status"] == "lag" and rows[0]["at"] == utc("19:31:00")   # not the 19:18 check
    p = (1 / 1.70) / (1 / 1.70 + 1 / 2.15)
    ok &= rows[0]["line_gap"] == 1.0 and rows[0]["side"] == "over" and math.isclose(rows[0]["ev_fair"], p * 1.87 - 1)
    return bool(ok)


def check_control(mod=M):
    b, ev, fresh, ft, team_of, us = run(mod)
    ctl = mod.controls(ev, b, ft, team_of)
    return sorted((u["book"], u["pid"]) for u in ctl) == [("dk", 3), ("fd", 3)]   # BBB only: AAA had Outs, C2 tips too soon


def test_guards():
    assert check_events() and check_track() and check_lag() and check_control()


def mutant(path, name, a, b, check):
    src = pathlib.Path(path).read_text()
    assert src.count(a) == 1, (name, a)
    d = pathlib.Path(tempfile.mkdtemp())
    (d / f"{name}.py").write_text(src.replace(a, b))
    sys.path.insert(0, str(d))
    try:
        m_ = importlib.import_module(name)
        try:
            return check(m_)
        except Exception:
            return False
    finally:
        sys.path.remove(str(d))
        sys.modules.pop(name, None)


def test_mutants():
    for tag, a, b, check in (
            ("fresh ignores the previous report", 'if s != "Out" or ps == "Out":', 'if s != "Out":', check_events),
            ("absence game 1 not required", "played_last = pg[prior[-1]].get(pid, (None, 0.0))[1] > 0", "played_last = True",
             check_events),
            ("tip too soon kept", "mins(pub, tip) < TIP_MIN else", "False else", check_events),
            ("news after the report counts", "if x[0] < pub]", "]", check_events),
            ("baseline after the report", "i = bisect.bisect_right(obs, pub) - 1", "i = bisect.bisect_right(obs, pub)", check_track),
            ("price ignored", "if st[0] == base[0] and abs(st[1] - base[1]) < P_MOVE:", "if st[0] == base[0]:", check_track),
            ("L at the report", "L = stale_before[-1] if stale_before else pub", "L = pub", check_track),
            ("opponents as teammates", 'if tm != ev["team"]:', "if False:", check_track),
            ("lag before the leader moved", 'after = [(t, c) for t, c in v["path"] if t > u["U"]]',
             'after = [(t, c) for t, c in v["path"]]', check_lag),
            ("EV on the other side", 'r["ev_fair"] = p * gs[2] - 1 if d == "up" else (1 - p) * gs[3] - 1',
             'r["ev_fair"] = (1 - p) * gs[3] - 1 if d == "up" else p * gs[2] - 1', check_lag),
            ("control keeps teams with Outs", "if tm is None or tm in hot:", "if tm is None:", check_control)):
        assert not mutant(M.__file__, "nba_injury_reaction_mut", a, b, check), tag


if __name__ == "__main__":
    test_guards()
    test_mutants()
    print("ok")
