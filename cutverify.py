"""Does pga_ruler.cut_rule() reproduce the MEASURED rule on every warehouse event?

A rule table written from a summary is a rule table that quietly rots on the one event whose
name does not match the pattern you had in mind. So this replays the identification from
cutmeasure2 and scores the shipped function against it, event by event, and prints every
disagreement rather than a pass rate alone.
"""
import sqlite3
import sys
from collections import defaultdict

import pga_ruler as RU

con = sqlite3.connect("file:pga_model.sqlite?mode=ro", uri=True, timeout=60)
con.row_factory = sqlite3.Row

P = defaultdict(lambda: defaultdict(dict))
meta = {}
for r in con.execute("SELECT event_id, event, date, player, rnd, score FROM rounds"):
    eid = str(r["event_id"])
    P[eid][r["player"]][int(r["rnd"])] = r["score"]
    if eid not in meta or str(r["date"]) < meta[eid][1]:
        meta[eid] = (r["event"] or "?", str(r["date"])[:10])

ok = bad = 0
fails, classes = [], defaultdict(int)
for eid, pl in P.items():
    nm, d0 = meta[eid]
    st = [sum(1 for p in pl.values() if r in p) for r in (1, 2, 3, 4)]
    if st[0] < 20:
        continue
    drop2 = st[1] and (st[2] / float(st[1])) < 0.93
    drop3 = st[2] and (st[3] / float(st[2])) < 0.93
    got = RU.cut_rule(nm, d0, n_field=st[0])

    if not drop2 and not drop3:
        cls, want = "NO_CUT", None
        good = got is None
    elif not drop2:
        classes["CUT_R3 (54-hole, unsupported by the sim)"] += 1
        continue
    else:
        tot = {p: v[1] + v[2] for p, v in pl.items() if 1 in v and 2 in v}
        adv = {p for p in pl if 3 in pl[p] and p in tot}
        if len(tot) < 30 or len(adv) < 10:
            continue
        S = max(tot[p] for p in adv)
        lo = sum(1 for t in tot.values() if t < S) + 1
        hi = sum(1 for t in tot.values() if t <= S)
        cls, want = "CUT_R2", "%d-%d" % (lo, hi)
        good = got is not None and lo <= got <= hi
    classes[cls] += 1
    if good:
        ok += 1
    else:
        bad += 1
        fails.append((d0, nm, cls, want, got, st))

print("classes: " + " · ".join("%s=%d" % (k, v) for k, v in sorted(classes.items())))
print("\ncut_rule() agrees with the measured rule on %d / %d events = %.3f"
      % (ok, ok + bad, ok / float(ok + bad)))

if fails:
    print("\nDISAGREEMENTS (%d):" % len(fails))
    print("  %-11s %-36s %-7s %-9s %-7s %s" % ("date", "event", "class", "measured", "rule", "R1/R2/R3/R4"))
    for d0, nm, cls, want, got, st in sorted(fails):
        print("  %-11s %-36s %-7s %-9s %-7s %d/%d/%d/%d"
              % (d0, nm[:36], cls, want if want else "no cut",
                 "no cut" if got is None else got, st[0], st[1], st[2], st[3]))

# The one that would be a live regression: a no-cut event the rule thinks cuts.
danger = [f for f in fails if f[2] == "NO_CUT"]
print("\n⚠️ NO-CUT events the rule would CUT (each one eliminates real players): %d" % len(danger))
for d0, nm, cls, want, got, st in danger:
    print("   %s  %s -> %s" % (d0, nm, got))

print("\nSPOT-CHECK of the name-collision traps:")
for nm, d in (("PGA Championship", "2026-05-14"), ("BMW PGA Championship", "2025-09-11"),
              ("BMW Australian PGA Championship", "2025-11-27"), ("BMW Championship", "2025-08-14"),
              ("The Open", "2026-07-16"), ("Genesis Scottish Open", "2026-07-09"),
              ("The Genesis Invitational", "2026-02-19"), ("Genesis Championship", "2025-10-23"),
              ("Masters Tournament", "2026-04-09"), ("Omega European Masters", "2025-08-28"),
              ("RBC Heritage", "2023-04-13"), ("RBC Heritage", "2026-04-16"),
              ("FedEx St. Jude Championship", "2026-08-13"),
              ("Some Brand New Open", None)):
    g = RU.cut_rule(nm, d)
    print("   %-34s %-11s -> %s" % (nm[:34], d or "(now)", "no cut" if g is None else g))

sys.exit(1 if danger else 0)
