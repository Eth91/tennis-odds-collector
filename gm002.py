#!/usr/bin/env python3
"""GM-002 — are the four rounds exchangeable? The model assumes they are.

pga_ruler draws all four rounds from ONE per-player distribution (mu, sigma) plus a shared
per-week effect. Nothing in it knows Thursday from Sunday. If scoring SPREAD differs by round,
the 72-hole distribution is the wrong shape, and that lands directly on top-N and win
probabilities -- not on the ranking, which is why an ordering metric would never see it.

THE SELECTION TRAP, which is the whole difficulty. Rounds 3 and 4 contain only cut-makers, and
they made the cut BECAUSE rounds 1-2 went well. So within cut-makers, R1 and R2 are TRUNCATED at
the top and their spread is artificially small. Comparing R1 spread to R4 spread on that cohort
measures the cut, not the golfer. Three comparisons are built so that each one holds selection
fixed:

    R1 vs R2   FULL FIELD. Everyone plays both regardless of anything, so no selection at all.
               This is the clean test of "Thursday is different".
    R3 vs R4   CUT-MAKERS. Both rounds have the identical cohort and both sit after the cut.
    all four   NO-CUT EVENTS ONLY. The only place R1 and R4 are directly comparable.

Scores are taken relative to that ROUND's own field mean, so course difficulty, setup and the
day's weather all cancel; what is left is the spread of players around the day.

LEG B asks the player-level version: do individual golfers have a repeatable round tendency
("Sunday players")? Tested the way SIG_SHRINK was -- between-player variance against sampling
noise -- because that method already showed that "some players are streakier" was 8% real and
mostly illusion, and the same illusion is available here.

2026 IS THE PROTECTED HOLDOUT AND IS NOT READ.
"""
import math
import sqlite3
from collections import defaultdict

import numpy as np

import pga_ruler as RU

con = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
rows = con.execute("SELECT event_id, event, date, player, rnd, score FROM rounds "
                   "WHERE date < '2026-01-01'").fetchall()
con.close()
print("rounds 2023-2025: %d" % len(rows))

ev = defaultdict(lambda: defaultdict(dict))       # event -> rnd -> player -> score
edate = {}
for eid, evn, d, pl, rnd, sc in rows:
    if sc is None:
        continue
    ev[eid][int(rnd)][pl] = float(sc)
    edate[eid] = str(d)
print("events: %d" % len(ev))

# field-relative score per (event, rnd, player)
rel = defaultdict(dict)
for eid, byr in ev.items():
    for rnd, d in byr.items():
        if len(d) < 30:
            continue
        m = float(np.mean(list(d.values())))
        for pl, s in d.items():
            rel[(eid, rnd)][pl] = s - m

nocut = [eid for eid, byr in ev.items()
         if 4 in byr and 1 in byr and len(byr[4]) >= 0.9 * len(byr[1]) and len(byr[1]) >= 30]
print("no-cut events (R4 field >= 90%% of R1): %d" % len(nocut))


def paired(pairs, label):
    """pairs: list of (sd_a, sd_b, n). Paired across events, so course/field cancel."""
    if len(pairs) < 8:
        print("   %-42s too few events (%d)" % (label, len(pairs)))
        return
    a = np.array([p[0] for p in pairs])
    b = np.array([p[1] for p in pairs])
    d = b - a
    se = d.std(ddof=1) / math.sqrt(len(d))
    print("   %-42s n=%3d events   sd %.3f -> %.3f   diff %+.4f (SE %.4f, t=%+.2f)"
          % (label, len(pairs), a.mean(), b.mean(), d.mean(), se,
             d.mean() / se if se > 0 else 0.0))


print("\n" + "=" * 94)
print("LEG A — does the SPREAD of scoring differ by round? (selection held fixed in each test)")
print("=" * 94)

# R1 vs R2, FULL FIELD — no selection whatsoever
p12 = []
for eid, byr in ev.items():
    if 1 not in byr or 2 not in byr:
        continue
    common = set(byr[1]) & set(byr[2])
    if len(common) < 40:
        continue
    a = np.array([rel[(eid, 1)][p] for p in common if p in rel[(eid, 1)]])
    b = np.array([rel[(eid, 2)][p] for p in common if p in rel[(eid, 2)]])
    if len(a) < 40 or len(b) < 40:
        continue
    p12.append((a.std(ddof=1), b.std(ddof=1), len(common)))
paired(p12, "R1 -> R2  (full field, no selection)")

# R3 vs R4, cut-makers — identical cohort, both post-cut
p34 = []
for eid, byr in ev.items():
    if 3 not in byr or 4 not in byr:
        continue
    common = set(byr[3]) & set(byr[4])
    if len(common) < 40:
        continue
    a = np.array([rel[(eid, 3)][p] for p in common if p in rel[(eid, 3)]])
    b = np.array([rel[(eid, 4)][p] for p in common if p in rel[(eid, 4)]])
    if len(a) < 40 or len(b) < 40:
        continue
    p34.append((a.std(ddof=1), b.std(ddof=1), len(common)))
paired(p34, "R3 -> R4  (cut-makers, same cohort)")

# all four, NO-CUT events only — the only clean R1 vs R4
print("\n   no-cut events only — the ONLY place R1 and R4 are directly comparable:")
for x, y in ((1, 2), (2, 3), (3, 4), (1, 4)):
    pp = []
    for eid in nocut:
        byr = ev[eid]
        if x not in byr or y not in byr:
            continue
        common = set(byr[x]) & set(byr[y])
        if len(common) < 30:
            continue
        a = np.array([rel[(eid, x)][p] for p in common if p in rel[(eid, x)]])
        b = np.array([rel[(eid, y)][p] for p in common if p in rel[(eid, y)]])
        if len(a) < 30 or len(b) < 30:
            continue
        pp.append((a.std(ddof=1), b.std(ddof=1), len(common)))
    paired(pp, "   R%d -> R%d (no-cut)" % (x, y))

print("\n" + "=" * 94)
print("LEG B — do individual players have a REPEATABLE round tendency?")
print("=" * 94)
# per player-round deviations, split by period
per = defaultdict(lambda: defaultdict(list))       # player -> rnd -> [rel score]
for (eid, rnd), d in rel.items():
    yr = int(edate[eid][:4])
    for pl, v in d.items():
        per[pl][(rnd, yr <= 2024)].append(v)

MINR = 12
tend1, tend2 = {}, {}
for pl, d in per.items():
    for early, store in ((True, tend1), (False, tend2)):
        r1 = d.get((1, early), [])
        r4 = d.get((4, early), [])
        if len(r1) >= MINR and len(r4) >= MINR:
            store[pl] = float(np.mean(r4)) - float(np.mean(r1))
both = sorted(set(tend1) & set(tend2))
print("   players with >=%d R1 and >=%d R4 rounds in BOTH periods: %d" % (MINR, MINR, len(both)))
if len(both) >= 30:
    a = np.array([tend1[p] for p in both])
    b = np.array([tend2[p] for p in both])
    r = float(np.corrcoef(a, b)[0, 1])
    print("   corr(R4-R1 tendency 2023-24, same 2025) = %+.3f   over %d players" % (r, len(both)))
    print("   tendency spread: early sd %.3f, late sd %.3f" % (a.std(), b.std()))
    # EB: how much of that spread could be sampling noise alone?
    noise = []
    for p in both:
        n1 = len(per[p][(1, True)]); n4 = len(per[p][(4, True)])
        v1 = np.var(per[p][(1, True)], ddof=1); v4 = np.var(per[p][(4, True)], ddof=1)
        noise.append(v1 / n1 + v4 / n4)
    mn = float(np.mean(noise))
    obs = float(a.var(ddof=1))
    true = max(obs - mn, 0.0)
    print("   observed variance of tendency %.4f | sampling noise %.4f | TRUE %.4f (sd %.3f)"
          % (obs, mn, true, math.sqrt(true)))
    print("   -> %.0f%% of the apparent spread in 'Sunday players' is sampling noise"
          % (100 * min(mn / obs, 1.0) if obs > 0 else 100))

print("\n" + "=" * 94)
print("PLACEBO — shuffle ROUND LABELS within each player-event")
print("=" * 94)
rng = np.random.default_rng(11)
pl_ev = defaultdict(list)
for (eid, rnd), d in rel.items():
    for pl, v in d.items():
        pl_ev[(eid, pl)].append((rnd, v))
sh = defaultdict(dict)
for (eid, pl), lst in pl_ev.items():
    rs = [r for r, _ in lst]
    vs = [v for _, v in lst]
    rng.shuffle(vs)
    for r_, v_ in zip(rs, vs):
        sh[(eid, r_)][pl] = v_
pp = []
for eid, byr in ev.items():
    if 1 not in byr or 2 not in byr:
        continue
    common = set(byr[1]) & set(byr[2])
    if len(common) < 40:
        continue
    a = np.array([sh[(eid, 1)][p] for p in common if p in sh[(eid, 1)]])
    b = np.array([sh[(eid, 2)][p] for p in common if p in sh[(eid, 2)]])
    if len(a) < 40 or len(b) < 40:
        continue
    pp.append((a.std(ddof=1), b.std(ddof=1), len(common)))
paired(pp, "R1 -> R2 with rounds SHUFFLED (must be null)")
