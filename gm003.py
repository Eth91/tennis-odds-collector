#!/usr/bin/env python3
"""GM-003 — is the round-variance rise STABLE, how big is it, and is it an artifact?

GM-002 found scoring spread grows through the tournament, on the two comparisons where selection
is held fixed, with a properly null placebo:
    R1 -> R2  sd 3.003 -> 3.070  t=+3.20   full field, nobody has been filtered yet
    R3 -> R4  sd 2.792 -> 2.851  t=+2.24   identical cut-maker cohort, both post-cut
The model draws all four rounds from ONE sigma, so if this is real the round-level distributions
are the wrong width -- too wide on Thursday, too narrow on Sunday.

Before believing it, four things have to be true, and each is a way the finding could die:

  1 STABLE OUT OF SAMPLE. Estimated on 2023-24, does the same shape appear in 2025?
    A pattern that only exists in the estimation period is a pattern of that period.
  2 NOT WITHDRAWALS. A player who quits mid-round or limps in injured posts a wild score, and
    later rounds are where that happens. Re-run trimmed, dropping the most extreme scores per
    round -- if the effect is 3 blowups an event it will vanish.
  3 NOT FIELD-SIZE OR EVENT MIX. R2 fields are the same size as R1, so this cannot be a count
    artifact, but the effect is re-checked separately in cut events and no-cut events.
  4 NOT MERELY CONDITIONS. Harder setups separate players more. Field mean score per round is the
    obvious proxy and is correlated against the spread directly -- if spread only rises when the
    day plays hard, this is weather and pin positions, not a round effect, and it belongs in a
    conditions term rather than a round term.

2026 IS THE PROTECTED HOLDOUT AND IS NOT READ.
"""
import math
import sqlite3
from collections import defaultdict

import numpy as np

import pga_ruler as RU

con = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
rows = con.execute("SELECT event_id, date, player, rnd, score FROM rounds "
                   "WHERE date < '2026-01-01'").fetchall()
con.close()

ev = defaultdict(lambda: defaultdict(dict))
edate = {}
for eid, d, pl, rnd, sc in rows:
    if sc is None:
        continue
    ev[eid][int(rnd)][pl] = float(sc)
    edate[eid] = str(d)
print("events %d, rounds %d" % (len(ev), len(rows)))


def spreads(eid, a, b, trim=0.0, cohort=None):
    """(sd_a, sd_b, mean_a, mean_b) on the SAME players, optionally trimmed."""
    byr = ev[eid]
    if a not in byr or b not in byr:
        return None
    common = (set(byr[a]) & set(byr[b])) if cohort is None else cohort
    common = [p for p in common if p in byr[a] and p in byr[b]]
    if len(common) < 40:
        return None
    x = np.array([byr[a][p] for p in common])
    y = np.array([byr[b][p] for p in common])
    if trim > 0:
        k = int(len(x) * trim)
        if k > 0:
            xs, ys = np.sort(x), np.sort(y)
            x = xs[k:len(xs) - k]
            y = ys[k:len(ys) - k]
    if len(x) < 30 or len(y) < 30:
        return None
    return x.std(ddof=1), y.std(ddof=1), x.mean(), y.mean()


def report(pairs, label):
    if len(pairs) < 8:
        print("   %-46s too few events (%d)" % (label, len(pairs)))
        return None
    a = np.array([p[0] for p in pairs]); b = np.array([p[1] for p in pairs])
    d = b - a
    se = d.std(ddof=1) / math.sqrt(len(d))
    t = d.mean() / se if se > 0 else 0.0
    print("   %-46s n=%3d  sd %.3f -> %.3f  %+.4f (t=%+.2f)  ratio %.4f"
          % (label, len(pairs), a.mean(), b.mean(), d.mean(), t, b.mean() / a.mean()))
    return dict(n=len(pairs), diff=d.mean(), t=t, ratio=b.mean() / a.mean())


def collect(years, a, b, trim=0.0, only=None):
    out = []
    for eid in ev:
        if int(edate[eid][:4]) not in years:
            continue
        if only == "cut" and len(ev[eid].get(4, {})) >= 0.9 * len(ev[eid].get(1, {}) or {1: 1}):
            continue
        if only == "nocut" and len(ev[eid].get(4, {})) < 0.9 * len(ev[eid].get(1, {}) or {1: 1}):
            continue
        s = spreads(eid, a, b, trim=trim)
        if s:
            out.append(s)
    return out


print("\n" + "=" * 96)
print("1 — CHRONOLOGICAL STABILITY: estimate on 2023-24, look for the same shape in 2025")
print("=" * 96)
for lbl, yrs in (("DEV  2023-24", {2023, 2024}), ("OOS  2025   ", {2025})):
    print("   %s" % lbl)
    report(collect(yrs, 1, 2), "      R1 -> R2 (full field)")
    report(collect(yrs, 3, 4), "      R3 -> R4 (cut-makers)")

print("\n" + "=" * 96)
print("2 — WITHDRAWALS / BLOWUPS: trim the extreme 5% of each tail")
print("=" * 96)
for tr in (0.0, 0.02, 0.05):
    print("   trim %.0f%%" % (100 * tr))
    report(collect({2023, 2024, 2025}, 1, 2, trim=tr), "      R1 -> R2")
    report(collect({2023, 2024, 2025}, 3, 4, trim=tr), "      R3 -> R4")

print("\n" + "=" * 96)
print("3 — EVENT MIX: cut events vs no-cut events separately")
print("=" * 96)
for only, lab in (("cut", "cut events"), ("nocut", "no-cut events")):
    print("   %s" % lab)
    report(collect({2023, 2024, 2025}, 1, 2, only=only), "      R1 -> R2")
    report(collect({2023, 2024, 2025}, 3, 4, only=only), "      R3 -> R4")

print("\n" + "=" * 96)
print("4 — IS IT JUST CONDITIONS? does spread track how HARD the day played?")
print("=" * 96)
pts = []
for eid, byr in ev.items():
    ms = {}
    for rnd, d in byr.items():
        if len(d) >= 40:
            v = np.array(list(d.values()))
            ms[rnd] = (v.mean(), v.std(ddof=1))
    if len(ms) < 2:
        continue
    mm = float(np.mean([m for m, _s in ms.values()]))
    for rnd, (m, s) in ms.items():
        pts.append((rnd, m - mm, s))
if pts:
    hard = np.array([p[1] for p in pts])
    sd = np.array([p[2] for p in pts])
    print("   corr(day played HARD vs event mean, spread that day) = %+.3f  over %d event-rounds"
          % (float(np.corrcoef(hard, sd)[0, 1]), len(pts)))
    print("   -> a strong positive says spread is a DIFFICULTY effect, not a round effect")
    # round effect AFTER removing difficulty
    A = np.column_stack([np.ones(len(pts)), hard])
    beta = np.linalg.lstsq(A, sd, rcond=None)[0]
    resid = sd - A @ beta
    print("\n   mean residual spread by round, difficulty partialled out:")
    for r_ in (1, 2, 3, 4):
        m = [x for (rr, _h, _s), x in zip(pts, resid) if rr == r_]
        if m:
            print("      R%d  n=%3d  %+.4f" % (r_, len(m), float(np.mean(m))))

print("\n" + "=" * 96)
print("PER-ROUND SIGMA MULTIPLIERS (relative to that event's own mean spread)")
print("=" * 96)
mult = defaultdict(list)
for eid, byr in ev.items():
    ms = {}
    for rnd, d in byr.items():
        if len(d) >= 40:
            ms[rnd] = float(np.std(list(d.values()), ddof=1))
    if len(ms) < 3:
        continue
    base = float(np.mean(list(ms.values())))
    if base <= 0:
        continue
    for rnd, s in ms.items():
        mult[(rnd, int(edate[eid][:4]))].append(s / base)
print("   %-6s %-22s %-22s %-22s" % ("round", "2023", "2024", "2025"))
for r_ in (1, 2, 3, 4):
    cells = []
    for y in (2023, 2024, 2025):
        v = mult.get((r_, y), [])
        cells.append(("%.4f (n=%d)" % (float(np.mean(v)), len(v))) if v else "-")
    print("   R%-5d %-22s %-22s %-22s" % (r_, cells[0], cells[1], cells[2]))
print("\n   NOTE R3/R4 multipliers are computed on the POST-CUT field and are NOT comparable to")
print("   R1/R2 in level -- only the year-to-year stability within a row is being read here.")
