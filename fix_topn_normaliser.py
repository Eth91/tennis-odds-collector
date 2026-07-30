"""Devig the top-N pools against the PRICED subset, not the whole field.

THE BUG. `fair_i = (1/od_i) * N_eff / inv` normalised a pool to the NOMINAL N (or, for the
ties products, to the whole field's expected qualifiers) while `inv` was summed over only the
runners FanDuel actually prices. Those are different populations. On the live board TOP_20 had
102 of 147 runners priced — and the model puts only 17.07 of the 20 slots on that subset, because
the 45 unpriced players are longshots who still collectively finish top-20 sometimes.

Normalising 17.07 slots' worth of runners as if they held 20 inflates every fair probability by
~17%. That is CONSERVATIVE for the edge (`ours - fair` comes out too small), which is why it
survived the earlier audits — it never manufactured an edge. But `ours / fair` is the RATIO GATE,
and inflating fair DEFLATES every ratio by ~15%. A bet reported at the 2.0 cap was really sitting
at 2.34, in the band where the model was measured to over-predict by 2.08-2.48x. The safety gate
was reading 15% low on exactly the market carrying 12 of the 15 live flags.

WHY THE MODEL'S OWN N_eff IS SAFE HERE, despite the obvious circularity worry. It is only being
asked for the SHARE of qualifiers sitting with the priced runners — a quantity dominated by
favourites, where this model is calibrated, not by the tail, where it is not. And it is checkable:
on the two markets FanDuel prices almost completely, the estimator lands on the known answer.

    market      priced  coverage   nominal N   model N_eff
    TOP_5         143      97%        5.0         4.92      (-1.6%)
    TOP_10        143      97%       10.0         9.82      (-1.8%)
    TOP_20        102      69%       20.0        17.07     (-14.6%)

Unbiased to under 2% where it can be verified, so it is trusted where it cannot.

INDEPENDENT CONFIRMATION FROM THE VIG. Implied overround is `inv / N_eff`. Under the old
normaliser the same book was apparently charging 8.9% on TOP_20 while charging 26.8% on TOP_5 and
18.7% on TOP_10 — not a thing any book does. With the priced-subset normaliser the family lines up
at 1.275 / 1.289 / 1.209. The incoherence WAS the bug; it is gone.

SECOND CHANGE — the pool guard. `inv > N_eff*3 or inv < N_eff*0.4` was a loose sanity net from
when N_eff was nominal. Now that N_eff and inv cover the same runners, `inv/N_eff` IS the implied
vig, so the guard becomes a direct plausibility test on it. Measured across all six live top-N
products: 1.209-1.373. The band [1.01, 1.75] admits those comfortably, rejects a book paying out
more than it takes (a data error), and still catches a duplicated or merged pool, which lands at
2.4x or worse. Strictly tighter than what it replaces.
"""
import ast
import io

p = "pga_e3.py"
s = io.open(p, encoding="utf-8").read()

anchor = "TN_RATIO_MIN = 1.15"
const = '''VIG_MIN = 1.01          # implied overround = inv / N_eff, now that both cover the SAME runners.
VIG_MAX = 1.75          # MEASURED across all six live top-N products: 1.209-1.373. Below 1.0 the
                        # book would be paying out more than it takes, which is a data error, not a
                        # gift. Above 1.75 the pool is not one N-winner market — duplicated or merged
                        # pools land at 2.4x+. Replaces the old inv-vs-3*N_eff net, which could not
                        # mean anything while N_eff and inv were counted over different populations.
'''
if "VIG_MAX" in s:
    print("  = VIG band already present")
else:
    assert anchor in s, "TN_RATIO_MIN anchor missing"
    s = s.replace(anchor, const + anchor, 1)

lines = s.split("\n")
try:
    i = next(k for k, l in enumerate(lines) if l.strip().startswith('is_ties = "TIE"'))
    j = next(k for k in range(i, i + 40)
             if 'if is_ties else {1: "win", 5: "top5"' in lines[k])
except StopIteration:
    raise AssertionError("N_eff block not found — pga_e3.py structure changed")
new = """        is_ties = "TIE" in str(mt).upper()
        key = ({1: "win_ties", 5: "top5_ties", 10: "top10_ties", 20: "top20_ties"}
               if is_ties else {1: "win", 5: "top5", 10: "top10", 20: "top20"})[N]
        if not any(key in (v or {}) for v in sim.values()):
            print(f"  skip {mt}: sim has no {key}")
            continue
        # NORMALISER OVER THE PRICED SUBSET (2026-07-30). `inv` only ever covered the runners the
        # book prices, so N_eff must too. Normalising 102 priced runners — who hold 17.07 of the 20
        # top-20 slots — as if they held all 20 inflated every fair by ~17%, which DEFLATED every
        # ours/fair ratio by ~15% and made the ratio gate read low on the market carrying most of
        # the board. Conservative for the edge, permissive for the safety gate; the gate matters.
        N_eff = sum((sim.get(run) or sim.get(RU.norm(run)) or {}).get(key, 0.0)
                    for run, _od in rr)
        if N_eff <= 0:
            continue
        inv = sum(1 / od for _, od in rr)
        _vig = inv / N_eff
        if not (VIG_MIN <= _vig <= VIG_MAX):
            # inv/N_eff is now a like-for-like overround, so an implausible value means the pool is
            # not one N-winner market (duplicated, merged, or partially collected).
            print(f"  skip {mt}: implied vig {_vig:.3f} outside [{VIG_MIN}, {VIG_MAX}] "
                  f"({len(rr)} priced, N_eff {N_eff:.2f})")
            continue
        print(f"  {mt}: {len(rr)} priced, N_eff {N_eff:.2f} (nominal {N}), implied vig {_vig:.3f}")"""
if "NORMALISER OVER THE PRICED SUBSET" in s:
    print("  = priced-subset normaliser already applied")
else:
    # splice by located line range rather than a literal match: the block contains a
    # continuation line whose indentation is easy to mis-transcribe, and a literal anchor
    # that silently fails to match is how the last two patch attempts died.
    # j is the SECOND line of the two-line `key = (...)` statement, so the statement ends AT j
    # and the tail resumes at j+1. Using j+2 here silently ate the `for run, od in rr:` line —
    # caught only because ast.parse runs before the write.
    s = "\n".join(lines[:i] + new.split("\n") + lines[j + 1:])

ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + pga_e3.py: N_eff over priced runners; pool guard is now an implied-vig band")
