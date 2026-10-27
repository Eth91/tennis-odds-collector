"""NBA_ROLE1_PREREG.md: the role model (team volume conserved, the absent player's minutes to his position group),
pricing (negative binomial, calibration toward the book), the ROLE_OPEN decision (spots are absence games 1-3,
the absent player listed out), its side-by-side replay (an opener after the report fires, one before it doesn't)
and the live pinger (install marks what is open, one ping per signal). MUTANTS in test_mutants()."""
import importlib
import pathlib
import sqlite3
import sys
import tempfile
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_replay as RP
import nba_role as ROLE
import nba_sxs_rules as SR
import test_nba_sxs as T

GROUPS = {1: "C", 2: "C", 3: "G", 4: "G", 5: "F", 6: "F", 7: "F", 8: "G", 9: "C"}
MINS = {1: 30, 2: 20, 3: 34, 4: 32, 5: 30, 6: 28, 7: 24, 8: 22, 9: 20}   # 240; X = 1, B = 2


def rows(n_games=6, x_missing=0, start=21):
    out = []
    for i in range(n_games):
        d = f"2026-10-{start + i:02d}"
        for pid, mn in MINS.items():
            if pid == 1 and i >= n_games - x_missing:
                continue                                    # X missed the last `x_missing` games
            out.append({"gid": f"g{i}", "date": d, "team": "HOM", "pid": pid, "min": float(mn), "fga": 0.4 * mn if pid != 1 else 14.0,
                        "fta": 0.1 * mn, "fg3a": 0.1 * mn, "fg3m": 0.035 * mn, "reb": 0.3 * mn if pid in (1, 2, 9) else 0.15 * mn,
                        "ast": 0.1 * mn, "pts": 0.45 * mn if pid != 1 else 20.0})
    return out


def rd(mod=ROLE, **kw):
    return types.SimpleNamespace(season=mod.Season(rows(**kw)), priors=mod.Priors([], GROUPS), groups=GROUPS, cache={})


def check(mod=ROLE):
    ok = True
    r = rd(mod)
    active = r.season.roster("HOM", "2026-10-27") - {1}
    proj = mod.project(r.season, r.priors, r.groups, "HOM", "2026-10-27", active, {1}, mode="v2")
    team_fga = sum(0.4 * m for p, m in MINS.items() if p != 1) + 14.0
    ok &= abs(sum(v["fga"] for v in proj.values()) - team_fga) < 1e-6                 # team volume conserved
    ok &= abs(sum(v["min"] for v in proj.values()) - 240.0) < 1e-6
    ok &= proj[2]["min"] - 20 > proj[8]["min"] - 22                                    # the backup C gains more than a G
    ok &= proj[2]["pts"] > 0.45 * 20                                                   # and scores more than his usual
    pts = lambda line, over=1.9, under=1.9, out=frozenset({1}), r_=r: mod.role_eval(r_, "2026-10-27", "HOM", 2, "points", line, over, under, out)
    ok &= [e["side"] for e in pts(4.5)] == ["over"]                                   # a soft opener: fires
    ok &= pts(8.5) == []                                                               # a fair one: calibrated EV < 5%
    ok &= pts(4.5, out=frozenset()) == []                                              # X not listed: no spot
    ok &= pts(4.5, r_=rd(mod, x_missing=3)) == []                                      # X has already missed 3: game 4, books adjusted
    ok &= [e["side"] for e in pts(4.5, r_=rd(mod, x_missing=2))] == ["over"]          # game 3: still a spot
    ok &= abs(mod.p_side(10.0, "points", 9.5, "over") + mod.p_side(10.0, "points", 9.5, "under") - 1) < 1e-9
    ok &= abs(mod.calibrated(0.9, 0.5, 0.0) - 0.5) < 1e-12 and abs(mod.calibrated(0.9, 0.5, 1.0) - 0.9) < 1e-12
    return bool(ok)


def test_role_model():
    assert check()


def day_stores(tmp):
    p = T.stores(tmp)
    m = sqlite3.connect(p["matchup"])
    for i in range(6):                                      # HOM's season so far: X 30, B 20, C 25, E 10
        g, d = f"S{i}", f"2026-10-{26 + i:02d}"
        m.execute("INSERT INTO games VALUES (?, '2026-27', ?, 'HOM', 'AWY', 100, 99)", (g, d))
        m.executemany("INSERT INTO player_games (gid, team, pid, min, pts, reb, ast, fg3m, fga, fta, fg3a) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      [(g, "HOM", T.X, 30, 20, 8, 3, 1, 15, 4, 3), (g, "HOM", T.B, 20, 8, 6, 1, 0, 7, 2, 1),
                       (g, "HOM", T.C, 25, 11, 4, 3, 1, 9, 2, 3), (g, "HOM", T.E, 10, 3, 2, 1, 0, 3, 1, 1)])
    m.commit()
    q = sqlite3.connect(p["lines"])                         # B's rebounds open on FanDuel after the report: 2.5
    q.executemany("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)",
                  [("2026-11-01T17:00:30", "fd", T.G, T.TIP, T.B, "", "rebounds", 2.5, s, 1.9) for s in ("over", "under")])
    q.commit()
    return p


def replay_role(mod_sr=SR):
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = day_stores(tmp)
    mod_sr.MATCHUP_DB, mod_sr.ROLE_GAMELOGS_DB = p["matchup"], p["gamelogs"]
    mod_sr._RD.clear()
    day = RP.Day(T.D, p["lines"], p["news"], p["matchup"], RP.History(p["gamelogs"], p["matchup"]))
    return [s for s in RP.run_day(day, [mod_sr.ROLE_OPEN()]) if s["rule"] == "ROLE_OPEN"]


def test_role_open_replay():
    try:
        sig = replay_role()
        assert [(s["pid"], s["market"], s["side"], s["line"], s["book"], s["t"]) for s in sig] == \
            [(T.B, "rebounds", "over", 2.5, "fd", "2026-11-01T17:00:30")], sig      # B's points opened at 15:00, before the news
    finally:
        SR._RD.clear()


def test_registry_covers_role_open():
    assert SR.REGISTRY["ROLE_OPEN"][1] == SR.fingerprint(SR.ROLE_OPEN) and SR.ROLE_OPEN.deps == SR.ROLE_DEPS


def test_live_pinger():
    import nba_role_open as L
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = day_stores(tmp)
    sent = []
    kw = dict(lines_db=p["lines"], news_db=p["news"], matchup_db=p["matchup"], gamelogs_db=p["gamelogs"], db=tmp / "role.sqlite",
              sender=lambda b: sent.append(b) or True)
    q = sqlite3.connect(p["lines"])
    q.execute("DELETE FROM quotes WHERE stat = 'rebounds'")
    q.commit()
    assert L.process(now="2026-11-01T16:00:00", **kw) == 0 and sent == []              # install: mark what is open
    q.executemany("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)",
                  [("2026-11-01T17:00:30", "fd", T.G, T.TIP, T.B, "Bee", "rebounds", 2.5, s, 1.9) for s in ("over", "under")])
    q.commit()
    assert L.process(now="2026-11-01T17:01:00", **kw) == 1 and len(sent) == 1
    assert sent[0].startswith("🟢 ROLE HOM Bee REB o2.5") and sent[0].endswith("shadow")
    assert L.process(now="2026-11-01T17:02:00", **kw) == 0 and len(sent) == 1           # once
    sqlite3.connect(p["lines"]).executemany("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)",
                                            [("2026-11-01T23:57:00", "fd", T.G, T.TIP, T.C, "Cee", "rebounds", 1.5, s, 1.9)
                                             for s in ("over", "under")]).connection.commit()
    assert L.process(now="2026-11-01T23:58:00", **kw) == 0                              # within 5 min of tip: never


def test_mutants():
    src = pathlib.Path(ROLE.__file__).read_text()
    for tag, a, b in (("no spot cap", "if n <= SPOT_MAX}", "}"),
                      ("calibration ignored", "        pc = calibrated(p_side(mu, market, line, side), q, BETA)\n",
                       "        pc = p_side(mu, market, line, side)\n"),
                      ("volume not conserved", "    scale = {s: (team_tot[s] / sum(raw[s].values())) if sum(raw[s].values()) > 0 else 1.0 for s in RATE_STATS}",
                       "    scale = {s: 1.0 for s in RATE_STATS}"),
                      ("no position weight", "(SAME_W if groups.get(p) and groups.get(p) == groups.get(x) else 1.0)", "1.0")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_role_mut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            assert not check(importlib.import_module("nba_role_mut")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_role_mut", None)
