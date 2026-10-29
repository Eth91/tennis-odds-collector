"""NBA_MINUTES_PREREG.md amendment 6: fix S (nba_minutes_v4.project_s: off is V3's minutes exactly; a = 1 gives X's minutes
to his position-mates only, by base; no position-mate or another group's a falls back to V3) and fix H (his minutes in
past team games every absent X sat while on the team, the last 10; the n / (n + k) blend). MUTANTS in test_mutants()."""
import importlib
import pathlib
import sys
import tempfile
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_minutes_v4 as V4
import nba_role as ROLE
import test_nba_role as TR

D = "2026-10-27"
LET = lambda p: {TR.GROUPS.get(p, "F")}


def check_slots(mod=V4, wowy=False):
    rs = TR.rows()
    if wowy:                                                # X sat game 4 and B played 30: V3's WOWY blend applies
        rs = [r for r in rs if not (r["pid"] == 1 and r["gid"] == "g3")]
        for r in rs:
            if r["pid"] == 2 and r["gid"] == "g3":
                r["min"] = 30.0
    se, pr = ROLE.Season(rs), ROLE.Priors([], TR.GROUPS)
    active = se.roster("HOM", D) - {1}
    run = lambda **kw: mod.project_s(se, pr, TR.GROUPS, "HOM", D, active, {1}, **kw)
    v3 = {p: v["min"] for p, v in ROLE.project(se, pr, TR.GROUPS, "HOM", D, active, {1}, mode="v3").items()}
    ok = run() == v3 and run(slots={"G": 0.0, "F": 0.0, "C": 0.0}, letters=LET) == v3   # off and a = 0: V3 exactly
    if wowy:
        return bool(ok)
    ok &= run(slots={"G": 1.0, "F": 1.0}, letters=LET) == v3                          # X is a C: another group's a does nothing
    act3 = se.roster("HOM", D) - {3}
    v3g = {p: v["min"] for p, v in ROLE.project(se, pr, TR.GROUPS, "HOM", D, act3, {3}, mode="v3").items()}
    ok &= mod.project_s(se, pr, TR.GROUPS, "HOM", D, act3, {3}, slots={"C": 1.0}, letters=LET) == v3g   # X a G: likewise
    ok &= run(slots={"C": 1.0}, letters=lambda p: {"C"} if p == 1 else {"G"}) == v3   # no position-mate active: V3
    s1 = run(slots={"C": 1.0}, letters=LET)                                            # all 30 to the Cs (2 and 9, 20 each)
    ok &= abs(s1[2] - 35.0) < 1e-6 and abs(s1[9] - 35.0) < 1e-6 and abs(s1[3] - 34.0) < 1e-6
    half = run(slots={"C": 0.5}, letters=LET)
    ok &= v3[2] < half[2] < s1[2] and s1[3] < half[3] < v3[3]
    ok &= abs(sum(half.values()) - 240.0) < 1e-6
    return bool(ok)


def test_slots():
    assert check_slots() and check_slots(wowy=True)


class FakeBD:
    """Team games (date, gid, season, box) and who was on the team when he missed one."""

    def __init__(self, games, off_team=()):
        self.games, self.off = games, set(off_team)

    def before(self, team, date):
        return [g for g in self.games if g[0] < date]

    def on_team_at(self, x, team, d, date):
        return (x, d) not in self.off


def box(**mins):
    return {int(k[1:]): {"min": float(v)} for k, v in mins.items() if v is not None}


def check_hist(mod=V4):
    g = [("2026-10-01", "a", "s", box(p7=10, p1=30)),          # X (1) played: not counted
         ("2026-10-02", "b", "s", box(p7=25)),                 # X sat, on the team: counted
         ("2026-10-03", "c", "s", box(p7=30)),                 # X sat but not on the team then: not counted
         ("2026-10-04", "d", "s", box(p8=20)),                 # X sat, he (7) did not play: not counted
         ("2026-10-05", "e", "s", box(p7=20, p2=22))]          # X sat, counted; 2 played
    bd = FakeBD(g, off_team={(1, "2026-10-03")})
    ok = mod.hist(bd, 7, "HOM", D, {1}) == (2, 22.5)
    ok &= mod.hist(bd, 7, "HOM", D, {1, 2}) == (1, 25.0)       # both absent players must have sat
    ok &= mod.hist(bd, 7, "HOM", "2026-10-05", {1}) == (1, 25.0)   # only games before the date
    many = [(f"2026-09-{i + 1:02d}", f"m{i}", "s", box(p7=10 + i)) for i in range(15)]
    ok &= mod.hist(FakeBD(many), 7, "HOM", D, {1}) == (10, sum(range(15, 25)) / 10)   # the last 10
    ok &= mod.with_hist(12.0, (0, 0.0), 3) == 12.0 and abs(mod.with_hist(12.0, (3, 24.0), 3) - 18.0) < 1e-12
    return bool(ok)


def test_hist():
    assert check_hist()


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
    for tag, a, b in (("slots ignore position", "for p in active if letters(p) & letters(x)}", "for p in active}"),
                      ("slots without the fallback", "a = slots.get(groups.get(x), 0.0) if ts else 0.0", "a = slots.get(groups.get(x), 0.0)"),
                      ("slots by the wrong group", "slots.get(groups.get(x), 0.0)", "slots.get(groups.get(p), 0.0)"),
                      ("slots share dropped", "+ a * same.get(p, 0.0) / ts)", ")"),
                      ("V3 parity: WOWY off", "        if g_:\n            w_ =", "        if False:\n            w_ ="),
                      ("V3 parity: no share factor", ") * share[(p, x)]\n    rot = set()", ")\n    rot = set()")):
        assert not mutant(V4.__file__, "nba_minutes_v4_mut", a, b, lambda m: check_slots(m) and check_slots(m, wowy=True)), tag
    for tag, a, b in (("hist ignores the team", " and bd.on_team_at(x, team, d, date) for x in absent)", " for x in absent)"),
                      ("hist ignores whether X sat", "all(not (x in b and b[x][\"min\"]) and", "all("),
                      ("hist uncapped", "    ms = ms[-HIST_N:]\n", ""),
                      ("hist blend unweighted", "w = n / (n + k) if n else 0.0", "w = 1.0 if n else 0.0")):
        assert not mutant(V4.__file__, "nba_minutes_v4_mut", a, b, check_hist), tag


def check_weights(mod=V4):
    """Amendment 7's fix B: pid 3 played 20 in g4 (a blowout), 34 otherwise. Down-weighting g4 raises his base; weights
    all 1 are V3; all 0 fall back to the plain mean."""
    rs = TR.rows()
    for r in rs:
        if r["pid"] == 3 and r["gid"] == "g4":
            r["min"] = 20.0
    se, pr = ROLE.Season(rs), ROLE.Priors([], TR.GROUPS)
    active = se.roster("HOM", D) - {1}
    run = lambda **kw: mod.project_s(se, pr, TR.GROUPS, "HOM", D, active, {1}, **kw)
    v3 = {p: v["min"] for p, v in ROLE.project(se, pr, TR.GROUPS, "HOM", D, active, {1}, mode="v3").items()}
    ok = run(wt=lambda g: 1.0) == v3 and run(wt=lambda g: 0.0) == v3
    up = run(wt=lambda g: 0.0 if g == "g4" else 1.0)
    ok &= up[3] > v3[3] + 1.0 and up[4] < v3[4]                 # his base 34, not 31.2; the 240 total takes it from others
    return bool(ok)


def check_margins(mod=None):
    import nba_blowout as B
    mod = mod or B
    rows_db = {"s": [{"gid": "a", "team": "HOM", "pts": 50.0}, {"gid": "a", "team": "HOM", "pts": 40.0},
                     {"gid": "a", "team": "AWY", "pts": 110.0}, {"gid": "b", "team": "HOM", "pts": 99.0}]}
    mg = mod.margins(rows_db)
    w = mod.weight(mg, 15, 0.25)
    return mg == {"a": 20.0} and w("a") == 0.25 and w("b") == 1.0 and mod.weight(mg, 25, 0.25)("a") == 1.0


def test_weights():
    assert check_weights() and check_margins()


def test_mutants_b():
    import nba_blowout as B
    for tag, a, b in (("weights ignored", "        if sum(ws):\n", "        if False:\n"),
                      ("no plain-mean fallback", "        if sum(ws):\n            base[p] = sum(w * b[p][\"min\"] for w, (_g, b) in zip(ws, last)) / sum(ws)",
                       "        if ws:\n            base[p] = sum(w * b[p][\"min\"] for w, (_g, b) in zip(ws, last)) / (sum(ws) or 1)")):
        assert not mutant(V4.__file__, "nba_minutes_v4_mut", a, b, check_weights), tag
    for tag, a, b in (("margin signed", "{g: abs(t[a] - t[b])", "{g: (t[a] - t[b])"),
                      ("blowout below M", "w if mg.get(gid, 0) >= m else 1.0", "w if mg.get(gid, 0) <= m else 1.0")):
        assert not mutant(B.__file__, "nba_blowout_mut", a, b, check_margins), tag
