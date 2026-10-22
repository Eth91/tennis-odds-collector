"""nba_flags priced-tier card slots: sticky, max 2 per team-game, P/R/A-disjoint.

Includes a MUTANT (the rule switched off) that must FAIL — a slot test that cannot see the
bug it guards is worthless (the first version of this check, a two-cycle replay, could not).
"""
import sys, tempfile, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_flags as F
def check(slot_open):
    sh = F._shadow(pathlib.Path(tempfile.mkdtemp()) / "s.sqlite")
    def put(team, b, stat):
        fid = f"priced|{b}|{stat}|10.5|D"
        if slot_open(sh, "D", {"team": team, "stat": stat}, fid):
            sh.execute("INSERT OR IGNORE INTO flags (flag_id, game_date, tier, team, b, stat) "
                       "VALUES (?,?,?,?,?,?)", (fid, "D", "priced", team, b, stat))
            return True
        return False
    cases = [
        ("first play takes slot 1",                      put("AAA", "p1", "points"),   True),
        ("disjoint 2nd play takes slot 2",               put("AAA", "p2", "rebounds"), True),
        ("3rd play: both slots held -> refused",         put("AAA", "p3", "assists"),  False),
        ("an incumbent re-flagged next cycle stays in",  put("AAA", "p1", "points"),   True),
        ("other team, first play",                       put("BBB", "q1", "points"),   True),
        ("other team, shares P with incumbent -> refused", put("BBB", "q2", "pra"),    False),
        ("other team, disjoint -> admitted",             put("BBB", "q3", "assists"),  True),
    ]
    ok = all(got == want for _, got, want in cases)
    for label, got, want in cases:
        print(f"   {'ok ' if got == want else 'BAD'} {label}: {got}")
    n = dict(sh.execute("select team, count(*) from flags group by team").fetchall())
    print(f"   rows per team: {n}")
    return ok





def test_real_rule_passes():
    assert check(F._priced_slot_open)


def test_mutant_is_caught():
    assert not check(lambda sh, d, f, fid: True)


if __name__ == "__main__":
    test_real_rule_passes(); test_mutant_is_caught(); print("test_nba_priced_slots: OK")
