#!/usr/bin/env python3
"""Cap the projected minutes bump — the only finding that replicated across samples.

Ledger: d_min 8+ went 4-13, −28.5 edge, −9.98u. Independent two-season corpus: the 8+ band was
the worst in BOTH seasons (−8.5 / −10.1). Nothing has tested actually excluding it.

The model has no pure d_min cap — BIG_JUMP_MIN only fires together with a thin sample
(n_elev < THIN_SAMPLE_N AND d_min > BIG_JUMP_MIN). Setting THIN_SAMPLE_N high in BOTH arms turns
that rule into a plain "skip when the bump exceeds X", which is the gate under test.

Faithful to the real pipeline: the cap is applied BEFORE current_selection, so dropping a play
frees its TOP-2 slot for the next-best one — exactly as a live gate would.
"""
import sys, sqlite3
sys.path.insert(0, "/home/ubuntu")
_a = list(sys.argv); sys.argv = ["x"]
import wnba_param_ab as AB
import wnba_tonight as T, wnba_wowy as W
sys.argv = _a

con = sqlite3.connect(f"file:{AB.R.HIST}?mode=ro", uri=True)
days = [d for (d,) in con.execute(
    "SELECT DISTINCT game_date FROM props WHERE game_date>='2026-05-10' "
    "AND game_date<='2026-08-05' ORDER BY 1")]
con.close()
players = W.players()

_orig_thin, _orig_jump = T.THIN_SAMPLE_N, T.BIG_JUMP_MIN
print(f"{len(days)} slates | shipped rule: skip when n_elev<{_orig_thin} AND d_min>{_orig_jump}")
print("candidate rule: skip when d_min > cap, regardless of sample\n")
print(f"{'cap':<10}{'record':>10}{'bets':>7}{'units':>10}{'vs base':>10}")

base_u = None
for cap in (None, 12.0, 10.0, 8.0, 6.0):
    if cap is None:
        T.THIN_SAMPLE_N, T.BIG_JUMP_MIN = _orig_thin, _orig_jump
        label = "shipped"
    else:
        T.THIN_SAMPLE_N, T.BIG_JUMP_MIN = 999, cap
        label = f"d_min<={cap:g}"
    rows = AB.run_arm(days, players, lambda: None)
    w, l, u = AB.tally(rows)
    if base_u is None:
        base_u = u
    print(f"{label:<10}{f'{w}-{l}':>10}{len(rows):>7}{u:>+10.2f}{u-base_u:>+10.2f}")

T.THIN_SAMPLE_N, T.BIG_JUMP_MIN = _orig_thin, _orig_jump
print("\nNOTE: 2026 only. Anything positive here needs the 2025 holdout before shipping —")
print("that gate killed the rebound edge tonight after it looked strong on one season.")
