"""NBA_INJURY_REACTION_PREREG.md amendment 1 guards for nba_injury_step2a.py: the conversion round-trips the main line,
excludes a push on a whole line and counts a half line from its floor; the gate differences the realized step; the fit
recovers a known dispersion (each prop's mean solved at its own line); C reads FanDuel's line at its first move (never the close), takes DraftKings' first check
after it and only when stale; B is points-type overs at FanDuel's first check; full CLV prices the bet line from the
close; the C null keeps stale control props only; a market that failed the gate is dropped. MUTANTS in test_mutants()."""
import importlib
import math
import pathlib
import sqlite3
import sys
import tempfile

import numpy as np
from scipy import stats

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_injury_reaction as R
import nba_injury_step2a as M
import test_nba_injury_reaction as T1


def check_conv(mod=M):
    c = mod.Conv(math.log(10), 0.0)
    m = c.mu(14.5, 0.5)
    k = 10.0
    ok = abs(float(mod.over_prob(14.5, np.array([m]), np.array([k]))[0]) - 0.5) < 1e-4
    ok &= c.p_at(14.5, 0.5, 15.5) < 0.5 < c.p_at(14.5, 0.5, 13.5) and c.p_at(14.5, 0.5, 14.5) == 0.5
    d = stats.nbinom(4.0, 4.0 / 7.0)                                         # mu 3, k 4
    ok &= math.isclose(float(mod.over_prob(3.0, np.array([3.0]), np.array([4.0]))[0]), d.sf(3) / (1 - d.pmf(3)), rel_tol=1e-9)
    ok &= math.isclose(float(mod.over_prob(2.5, np.array([3.0]), np.array([4.0]))[0]), d.sf(2), rel_tol=1e-9)
    ok &= float(mod.over_prob(-0.5, np.array([3.0]), np.array([4.0]))[0]) == 1.0
    e = stats.nbinom(4.5, 4.5 / 7.5)                                         # a real (non-integer) size: mu 3, k 4.5
    ok &= math.isclose(float(mod.over_prob(2.5, np.array([3.0]), np.array([4.5]))[0]), e.sf(2), rel_tol=1e-9)
    ok &= math.isclose(float(mod.over_prob(2.0, np.array([3.0]), np.array([4.5]))[0]), e.sf(2) / (1 - e.pmf(2)), rel_tol=1e-9)
    return bool(ok)


def check_steps(mod=M):
    c = mod.Conv(math.log(10), 0.0)
    L = np.array([2.5, 2.5, 2.5, 2.5])
    P = np.array([0.5, 0.5, 0.5, 0.5])
    Y = np.array([1.0, 3.0, 4.0, 5.0])
    st = mod.steps(c, L, P, Y, (-1, 1))
    pred = c.p_at(2.5, 0.5, 3.5) - 0.5
    return math.isclose(st[1][0], pred, rel_tol=1e-6) and math.isclose(st[1][1], 0.5 - 0.75) and math.isclose(st[-1][1], 0.0)


def check_fit(mod=M):
    rng = np.random.default_rng(3)
    mu = rng.uniform(4, 25, 2000)
    k = 8.0
    L = np.floor(mu) + 0.5
    P = np.array([stats.nbinom(k, k / (k + m)).sf(math.floor(l)) for m, l in zip(mu, L)])
    Y = rng.negative_binomial(k, k / (k + mu)).astype(float)
    (a, b), _ = mod.fit(L, P, Y)
    return abs(a + b * math.log(12) - math.log(k)) < 0.25 and abs(b) < 0.5


def fixture():
    l, n, m = T1.fixture()
    con = sqlite3.connect(l)
    q = [("19:14:00", "fd", 2, "pra", 30.5, 1.87, 1.87), ("19:20:00", "fd", 2, "pra", 30.5, None, None),
         ("19:20:00", "fd", 2, "pra", 31.5, 1.87, 1.87),
         ("19:15:00", "dk", 2, "pra", 30.5, 1.87, 1.87), ("19:18:00", "dk", 2, "pra", 30.5, None, None),
         ("19:18:00", "dk", 2, "pra", 31.5, 1.87, 1.87),              # DraftKings moved before FanDuel: no C flag
         ("19:15:00", "dk", 3, "rebounds", 7.5, 1.87, 1.87), ("19:31:00", "dk", 3, "rebounds", 7.5, None, None),
         ("19:31:00", "dk", 3, "rebounds", 8.5, 1.87, 1.87),          # a control prop moving at the flag time
         ("23:50:00", "fd", 2, "points", 15.5, None, None), ("23:50:00", "fd", 2, "points", 13.5, 1.87, 1.87)]
    for t, book, pid, stat, line, o, u in q:          # FanDuel's close goes the other way: C must not read it
        con.executemany("INSERT INTO quotes VALUES (?, ?, 'G3', ?, ?, ?, ?, ?, ?, ?)",
                        [(f"2026-10-27T{t}", book, T1.TIP, pid, f"P{pid}", stat, line, side, odds)
                         for side, odds in (("over", o), ("under", u))])
    con.commit()
    con.close()
    return l, n, m


def run(mod):
    l, n, m = fixture()
    b = R.Boards(l)
    ev, fresh, ft, team_of = R.load_events(n, m, b)
    us, _ = R.units(ev, b, team_of)
    ctl = R.controls(ev, b, ft, team_of)
    return b, us, ctl


def check_candidates(mod=M):
    b, us, ctl = run(mod)
    fc, fb = mod.candidates_c(us, b), mod.candidates_b(us, b)
    ok = len(fc) == 1 and fc[0]["stat"] == "points" and fc[0]["at"] == T1.utc("19:31:00") and fc[0]["side"] == "over"
    ok &= fc[0]["line"] == 14.5 and fc[0]["odds"] == 1.87 and fc[0]["tf"] == T1.utc("19:20:00")
    ok &= sorted(f["stat"] for f in fb) == ["points", "pra"] and all(f["side"] == "over" and f["at"] == T1.utc("19:17:00") for f in fb)
    nc = mod.null_c(ctl, b, fc)
    ok &= len(nc) == 1 and nc[0]["stat"] == "points" and [x[0] for x in nc[0]["legs"]] == ["over", "under"]
    return bool(ok)


def check_clv(mod=M):
    b, us, ctl = run(mod)
    fc = mod.candidates_c(us, b)
    c = mod.Conv(math.log(10), 0.0)
    want = c.p_at(15.5, 0.5, 14.5) * 1.87 - 1                              # DraftKings closed 15.5 at even
    convs = {m: c for m in mod.MARKETS}
    kept, drops = mod.score([dict(f) for f in fc], convs, set(mod.MARKETS))
    ok = len(kept) == 1 and math.isclose(kept[0]["clv"], want, rel_tol=1e-9) and want > 0
    ok &= math.isclose(mod.full_clv(c, (15.5, 0.5, 1.87, 1.87, ()), 14.5, "under", 2.0), (1 - c.p_at(15.5, 0.5, 14.5)) * 2.0 - 1)
    kept2, drops2 = mod.score([dict(f) for f in fc], convs, set())
    ok &= kept2 == [] and drops2 == {"market failed the gate": 1}
    return bool(ok)


def test_guards():
    assert check_conv() and check_steps() and check_fit() and check_candidates() and check_clv()


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
            ("push counted", "return special.betainc(line + 1, k, 1 - q) / (1 - np.exp(nb_logpmf(line, mu, k)))",
             "return special.betainc(line + 1, k, 1 - q)", check_conv),
            ("half line from its ceiling", "return special.betainc(math.floor(line) + 1, k, 1 - q)",
             "return special.betainc(math.ceil(line) + 1, k, 1 - q)", check_conv),
            ("size truncated (nbdtrc)", "return special.betainc(math.floor(line) + 1, k, 1 - q)",
             "return special.nbdtrc(math.floor(line), k, q)", check_conv),
            ("realized step not differenced", "float(np.mean(Y > L + d)) - base", "float(np.mean(Y > L + d))", check_steps),
            ("mean solved at the wrong line", "r = conv.row(line)", "r = conv.row(float(L[0]))", check_fit),
            ("C side from FanDuel's close", 'tf, side, kind = t, ("over" if st[0] > base[0] else "under"), "line"',
             'tf, side, kind = t, ("over" if fu["close"][0] > base[0] else "under"), "line"', check_candidates),
            ("C takes a check before FanDuel moved", 'nxt = [(t, c) for t, c in du["path"] if t > tf]',
             'nxt = [(t, c) for t, c in du["path"]]', check_candidates),
            ("C without DraftKings stale", 'if not nxt or nxt[0][1] != "stale":', "if not nxt:", check_candidates),
            ("B in every market", 'for u in us:\n        if u["book"] != "fd" or u["stat"] not in BIG or not u["path"]:',
             'for u in us:\n        if u["book"] != "fd" or not u["path"]:', check_candidates),
            ("C null keeps moved props", 'if t in ats and c == "stale":', "if t in ats:", check_candidates),
            ("CLV ignores the line", "p = conv.p_at(close[0], close[1], line)", "p = close[1]", check_clv),
            ("gate not applied", 'if r["stat"] not in usable:', "if False:", check_clv)):
        assert not mutant(M.__file__, "nba_injury_step2a_mut", a, b, check), tag


if __name__ == "__main__":
    test_guards()
    test_mutants()
    print("ok")
