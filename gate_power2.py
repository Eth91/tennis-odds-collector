"""Corrected G2 power curve.

The first run calibrated the "bad" book to sit EXACTLY at the gate's 2.0-point threshold, so a
~50% pass rate at every n is arithmetically correct rather than evidence of no power. Redone
across a range of true gaps: for each, how often does the gate (PASS if gap <= 2.0) let it
through? That gives the n needed to detect a book that is genuinely sharper.
"""
import math, random, sqlite3, statistics as st
import pga_ruler as RU
random.seed(11)

con = sqlite3.connect(RU.DB)
evs = con.execute("SELECT event_id, MIN(date) d FROM rounds GROUP BY event_id "
                  "HAVING d >= '2026-01-01' ORDER BY d").fetchall()
con.close()
rows = RU.all_rows()
pairs = []
for eid, d0 in evs:
    R, _ = RU.fit(asof=d0, rows=rows)
    Rn = {RU.norm(k): v for k, v in R.items()}
    con = sqlite3.connect(RU.DB)
    rr = con.execute("SELECT player, SUM(score), COUNT(*) FROM rounds WHERE event_id=? "
                     "AND score>0 GROUP BY player", (eid,)).fetchall()
    con.close()
    fin = [(RU.norm(p), t) for p, t, n in rr if n == 4 and t]
    fin = [(p, t) for p, t in fin if p in Rn]
    if len(fin) < 20:
        continue
    for _ in range(200):
        (a, ta), (b, tb) = random.choice(fin), random.choice(fin)
        if a == b or ta == tb:
            continue
        p = RU.matchup_prob(Rn, a, b, rounds=4)
        if p is not None:
            pairs.append((min(max(p, 1e-6), 1 - 1e-6), 1.0 if ta < tb else 0.0))
print("pairs: %d" % len(pairs))
ll_r = [-(y * math.log(p) + (1 - y) * math.log(1 - p)) for p, y in pairs]


def book_ll(shift):
    o = []
    for p, y in pairs:
        q = min(max(p + shift * (y - p), 1e-6), 1 - 1e-6)
        o.append(-(y * math.log(q) + (1 - y) * math.log(1 - q)))
    return o


def shift_for(target_pts):
    lo, hi = 0.0, 0.95
    for _ in range(50):
        mid = (lo + hi) / 2
        if (st.mean(ll_r) - st.mean(book_ll(mid))) * 100 < target_pts:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


print()
print("G2 PASS if (ruler_ll - book_ll) <= 2.0 pts. 2000 resamples. Rows = the TRUE gap.")
print("  %-12s %s" % ("true gap", "  ".join("n=%-5d" % n for n in (15, 30, 60, 120, 250, 500))))
for gap in (0.0, 1.0, 2.0, 4.0, 6.0, 10.0):
    d = [a - b for a, b in zip(ll_r, book_ll(shift_for(gap)))]
    cells = []
    for n in (15, 30, 60, 120, 250, 500):
        pr = sum(1 for _ in range(2000)
                 if st.mean(random.choices(d, k=n)) * 100 <= 2.0) / 2000
        cells.append("%5.1f%%" % (100 * pr))
    tag = "  <- want PASS" if gap <= 1.0 else ("  <- want FAIL" if gap >= 4 else "  (boundary)")
    print("  %+6.1f pts   %s%s" % (gap, "  ".join(cells), tag))
print()
print("Read the FAIL rows: the n where pass-rate drops under 10% is the n G2 actually needs")
print("to catch a book that much sharper.")
