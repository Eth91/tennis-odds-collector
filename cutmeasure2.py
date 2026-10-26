"""What cut rule does each event ACTUALLY use? Corrected measurement.

TWO BUGS IN THE FIRST PASS, both of which made the answer look like noise:
 1. TIES MAKE N NON-IDENTIFIED. If the cut line is score S, then "top N and ties" produces the
    SAME advancing set for every N in (count(tot<S), count(tot<=S)]. Scanning N and keeping the
    first perfect match therefore always reported the SMALLEST consistent N, which is why the
    distribution looked spread over 40-70 with agreement 1.000 everywhere. The identified
    quantity is the RANGE, so that is what this reports, and the question becomes "is 65 in it".
 2. THE DROP IS NOT ALWAYS AFTER R2. The American Express (156/156/156/69) and Pebble Beach
    (154/153/148/75) are pro-ams that cut after 54 HOLES. Classifying on R2->R3 alone called
    them no-cut. Where the drop happens is part of the classification, not an assumption.

WD BIAS is reported, not hidden: a player who makes the cut and withdraws has no R3, so the
observed line can only be too STRICT. Events where that matters are flagged.
"""
import sqlite3
from collections import defaultdict

con = sqlite3.connect("file:pga_model.sqlite?mode=ro", uri=True, timeout=60)
con.row_factory = sqlite3.Row

P = defaultdict(lambda: defaultdict(dict))
meta = {}
for r in con.execute("SELECT event_id, event, date, player, rnd, score FROM rounds"):
    eid = str(r["event_id"])
    P[eid][r["player"]][int(r["rnd"])] = r["score"]
    if eid not in meta or str(r["date"]) < meta[eid][1]:
        meta[eid] = (r["event"] or "?", str(r["date"])[:10])

out = []
for eid, pl in P.items():
    nm, d0 = meta[eid]
    st = [sum(1 for p in pl.values() if r in p) for r in (1, 2, 3, 4)]
    if st[0] < 20:
        continue

    # Where does the field shrink? >7% loss is a cut; WD attrition alone never approaches it.
    drop2 = st[1] and (st[2] / float(st[1])) < 0.93
    drop3 = st[2] and (st[3] / float(st[2])) < 0.93

    if not drop2 and not drop3:
        out.append((d0, nm, st, "NO_CUT", None, None, 0)); continue
    if not drop2 and drop3:
        out.append((d0, nm, st, "CUT_R3", None, None, 0)); continue

    tot = {p: v[1] + v[2] for p, v in pl.items() if 1 in v and 2 in v}
    r3 = {p for p in pl if 3 in pl[p]}
    adv = {p for p in r3 if p in tot}
    if len(tot) < 30 or len(adv) < 10:
        continue

    S = max(tot[p] for p in adv)                       # observed cut line
    lo = sum(1 for t in tot.values() if t < S) + 1     # smallest consistent N
    hi = sum(1 for t in tot.values() if t <= S)        # largest consistent N
    wd = sum(1 for p, t in tot.items() if t <= S and p not in adv)   # cut-makers absent from R3
    out.append((d0, nm, st, "CUT_R2", lo, hi, wd))

out.sort()
print("%-11s %-33s %4s %4s %4s %4s  %-7s %-12s %s"
      % ("date", "event", "R1", "R2", "R3", "R4", "class", "N range", "wd"))
print("-" * 108)
for d0, nm, st, cl, lo, hi, wd in out:
    rng = "-" if lo is None else ("%d-%d" % (lo, hi))
    print("%-11s %-33s %4d %4d %4d %4d  %-7s %-12s %s"
          % (d0, nm[:33], st[0], st[1], st[2], st[3], cl, rng, wd or ""))

cut2 = [o for o in out if o[3] == "CUT_R2"]
print("\n" + "=" * 70)
print("CLASSES: " + " · ".join("%s=%d" % (c, sum(1 for o in out if o[3] == c))
                               for c in ("CUT_R2", "CUT_R3", "NO_CUT")))

print("\nIS THE STANDARD RULE CONSISTENT WITH THE DATA? (share of CUT_R2 events whose")
print("identified N-range CONTAINS the candidate rule)")
for cand in (50, 55, 60, 65, 70):
    ok = sum(1 for o in cut2 if o[4] <= cand <= o[5])
    print("   top-%d and ties : %3d / %3d = %.3f" % (cand, ok, len(cut2), ok / float(len(cut2))))

print("\nSAME, BY SEASON (the rule changed to 65 in 2024)")
for yr in ("2023", "2024", "2025", "2026"):
    v = [o for o in cut2 if o[0].startswith(yr)]
    if not v:
        continue
    line = "   %s n=%3d :" % (yr, len(v))
    for cand in (50, 65, 70):
        line += "  top%d %.3f" % (cand, sum(1 for o in v if o[4] <= cand <= o[5]) / float(len(v)))
    print(line)

print("\nEVENTS WHERE 65 IS *NOT* CONSISTENT (these need their own rule):")
bad = [o for o in cut2 if not (o[4] <= 65 <= o[5])]
agg = defaultdict(list)
for d0, nm, st, cl, lo, hi, wd in bad:
    agg[nm].append((d0[:4], lo, hi))
for nm in sorted(agg, key=lambda x: -len(agg[x])):
    v = agg[nm]
    print("   %-38s %dx  %s" % (nm[:38], len(v), ", ".join("%s:%d-%d" % x for x in v[:5])))

print("\nNO-CUT / 54-HOLE-CUT EVENTS (the sim must NOT apply a 36-hole cut to these):")
for cl in ("NO_CUT", "CUT_R3"):
    agg2 = defaultdict(int)
    for o in out:
        if o[3] == cl:
            agg2[o[1]] += 1
    print("  %s:" % cl)
    for nm, c in sorted(agg2.items(), key=lambda x: -x[1]):
        print("     %-42s %dx" % (nm[:42], c))
