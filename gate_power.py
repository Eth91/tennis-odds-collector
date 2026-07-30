"""Do the two money gates have the statistical power to decide anything?

Neither G2 (n>=15, ruler log-loss within 2 points of the book) nor the E1 tripwire (n>=25,
bench below a win-rate threshold) was ever power-analysed. Both were picked as round numbers.
A gate with no power is worse than no gate: it produces a verdict that reads as evidence.

G2: simulate the test under two worlds — the ruler is exactly as good as the book (null), and
the ruler is 2 points worse (the thing the gate is meant to catch) — using the ruler's REAL
out-of-sample matchup probabilities from the walk-forward, so the log-loss variance is the
actual one and not an assumption. Then ask, at each n: how often does the gate say PASS?
A useful gate passes the null often and the bad model rarely.

E1: the tripwire fires when the observed win rate falls below its threshold. With a binomial
SE of sqrt(p(1-p)/n), ask how often it fires on a stream that is exactly break-even (a false
bench) and on one that is genuinely broken (a true catch).
"""
import math
import random
import sqlite3
import statistics as st
from collections import defaultdict

import pga_ruler as RU

random.seed(7)


def _phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2)))


# ---------------------------------------------------------------- real matchup probs
def ruler_pairs(seasons=(2026,), limit=4000):
    """[(p_ruler, outcome)] on real out-of-sample 72-hole-style pairs."""
    con = sqlite3.connect(RU.DB)
    evs = con.execute("SELECT event_id, MIN(date) d FROM rounds GROUP BY event_id "
                      "HAVING d >= ? ORDER BY d", ("%d-01-01" % min(seasons),)).fetchall()
    con.close()
    rows = RU.all_rows()
    out = []
    for eid, d0 in evs:
        R, _ = RU.fit(asof=d0, rows=rows)
        Rn = {RU.norm(k): v for k, v in R.items()}
        con = sqlite3.connect(RU.DB)
        rr = con.execute("SELECT player, SUM(score), COUNT(*) FROM rounds WHERE event_id=? "
                         "AND score>0 GROUP BY player", (eid,)).fetchall()
        con.close()
        fin = [(RU.norm(p), tot) for p, tot, n in rr if n == 4 and tot]
        fin = [(p, t) for p, t in fin if p in Rn]
        if len(fin) < 20:
            continue
        for _ in range(min(200, len(fin) * 2)):
            (a, ta), (b, tb) = random.choice(fin), random.choice(fin)
            if a == b or ta == tb:
                continue
            p = RU.matchup_prob(Rn, a, b, rounds=4)
            if p is None:
                continue
            out.append((min(max(p, 1e-6), 1 - 1e-6), 1.0 if ta < tb else 0.0))
        if len(out) >= limit:
            break
    return out


print("=" * 74)
print("GATE POWER ANALYSIS")
print("=" * 74)
pairs = ruler_pairs()
print("real out-of-sample matchup pairs available: %d" % len(pairs))
if len(pairs) < 200:
    raise SystemExit("not enough pairs")

ll_r = [-(y * math.log(p) + (1 - y) * math.log(1 - p)) for p, y in pairs]
print("ruler per-observation log-loss: mean %.4f  sd %.4f" % (st.mean(ll_r), st.pstdev(ll_r)))

# A book that is exactly as good (null) and one 2pts worse. Model the book's probability as
# the ruler's, nudged toward/away from the outcome to hit a target log-loss difference.
def book_ll(pairs, shift):
    """Book log-loss where `shift` moves its probability toward the truth by that much."""
    out = []
    for p, y in pairs:
        q = p + shift * (y - p)          # shift>0 => sharper than the ruler
        q = min(max(q, 1e-6), 1 - 1e-6)
        out.append(-(y * math.log(q) + (1 - y) * math.log(1 - q)))
    return out


# calibrate the shift so the mean gap is ~2 points (the gate's own FAIL threshold)
lo, hi = 0.0, 0.9
for _ in range(40):
    mid = (lo + hi) / 2
    gap = (st.mean(ll_r) - st.mean(book_ll(pairs, mid))) * 100
    if gap < 2.0:
        lo = mid
    else:
        hi = mid
shift2 = (lo + hi) / 2
print("a book %.1f pts sharper than the ruler corresponds to shift=%.4f"
      % ((st.mean(ll_r) - st.mean(book_ll(pairs, shift2))) * 100, shift2))

ll_null = book_ll(pairs, 0.0)          # book exactly as good as the ruler
ll_bad = book_ll(pairs, shift2)        # book 2pts sharper => ruler should FAIL

print()
print("G2 gate: PASS if (ruler_ll - book_ll) <= 2.0 pts.  1000 resamples per n.")
print("  %5s | %-28s | %-28s" % ("n", "book EQUAL to ruler (want PASS)",
                                 "book 2pts SHARPER (want FAIL)"))
d_null = [a - b for a, b in zip(ll_r, ll_null)]
d_bad = [a - b for a, b in zip(ll_r, ll_bad)]
for n in (15, 30, 60, 120, 250, 500, 1000):
    for label, d in (("null", d_null), ("bad", d_bad)):
        pass
    p_null = sum(1 for _ in range(1000)
                 if st.mean(random.choices(d_null, k=n)) * 100 <= 2.0) / 1000
    p_bad = sum(1 for _ in range(1000)
                if st.mean(random.choices(d_bad, k=n)) * 100 <= 2.0) / 1000
    flag = ""
    if p_null >= 0.90 and p_bad <= 0.10:
        flag = "  <- USABLE"
    print("  %5d | PASS %5.1f%%%18s | PASS %5.1f%% (false pass)%s"
          % (n, 100 * p_null, "", 100 * p_bad, flag))
print()
print("  A gate is only usable where it passes the good book >=90% AND fails the bad one >=90%.")

# --------------------------------------------------------------- E1 tripwire power
print()
print("E1 tripwire: fires when win rate < 0.52*be*2 = 1.04*be (the CODE; the docstring says")
print("             '52% of breakeven', i.e. 0.52*be — the two differ by 4x).")
avg_odds = 1.91
be = 1 / avg_odds
thr = 0.52 * be * 2
print("  avg odds %.2f -> breakeven %.3f, tripwire threshold %.3f" % (avg_odds, be, thr))
print()
print("  %5s | %-26s | %-26s" % ("n", "stream EXACTLY breakeven", "stream BROKEN (be-8pts)"))
for n in (25, 50, 100, 250, 600):
    se = math.sqrt(be * (1 - be) / n)
    p_false = _phi((thr - be) / se)                       # fires on a fine stream
    p_true = _phi((thr - (be - 0.08)) / se)               # fires on a broken one
    flag = "  <- USABLE" if p_false <= 0.10 and p_true >= 0.90 else ""
    print("  %5d | fires %5.1f%% (FALSE bench)   | fires %5.1f%% (true catch)%s"
          % (n, 100 * p_false, 100 * p_true, flag))
print()
print("  At n=25 the tripwire benches a perfectly break-even stream more often than not:")
print("  it is a coin flip dressed as a safety mechanism.")
