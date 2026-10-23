"""nba_flags.absence_index: the trigger's absence count, incl. tomorrow's games and the season
boundary. A mutant that ignores tonight's Out (the h1 rule) must fail."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_flags as F

TEAM = ["2026-04-08", "2026-04-10", "2026-04-12", "2026-10-21", "2026-10-23", "2026-10-25"]
SEASON = 2026
CASES = [  # (label, last_app, team dates completed so far, out tonight & playing, expected)
    ("played the team's last game -> absence 1", "2026-10-23", TEAM[:5], False, 1),
    ("missed one completed game -> absence 2", "2026-10-21", TEAM[:5], False, 2),
    ("h1: played last game, Out tonight too -> absence 2", "2026-10-23", TEAM[:5], True, 2),
    ("h1: missed one AND Out tonight -> absence 3 (excluded)", "2026-10-21", TEAM[:5], True, 3),
    ("season boundary: sat Apr 10/12, no game yet this season -> 1", "2026-04-08", TEAM[:3], False, 1),
    ("season boundary: sat April, missed this season's opener -> 2", "2026-04-08", TEAM[:4], False, 2),
    ("long-term: out since February (25 games) -> carried, excluded", "2026-02-01",
     [f"2026-02-{d:02d}" for d in range(3, 28)] + ["2026-10-21"], False, 27),
]


def run(fn):
    ok = True
    for label, last, dates, tonight, want in CASES:
        got = fn(last, dates, SEASON, tonight)
        ok &= got == want
        print(f"   {'ok ' if got == want else 'BAD'} {label}: {got}")
    return ok


def test_real():
    assert run(F.absence_index)


def test_mutant_ignores_tonights_out():
    assert not run(lambda last, dates, season, tonight: F.absence_index(last, dates, season, False))


if __name__ == "__main__":
    print("REAL:"); test_real()
    print("MUTANT (ignores tonight's Out) — must fail:"); test_mutant_ignores_tonights_out()
    print("test_nba_absence: OK")


def test_mutant_full_season_reset_fails():
    """The first rule reset EVERY streak at the boundary, calling a February injury fresh."""
    def full_reset(last, dates, season, tonight):
        return 1 + sum(1 for d in dates if d > last and F.C.season_of(d) == season) + (1 if tonight else 0)
    assert not run(full_reset)
