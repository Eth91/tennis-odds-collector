#!/usr/bin/env python3
"""EXP-012 step 1 — WHAT DOES "2nd Round Leader" SETTLE ON? Resolve it before grading anything.

Two live readings, and they are not close to equivalent:
  (a) lowest score IN round 2      — an 18-hole market, the direct analogue of 1st Round Leader
  (b) lowest 36-hole total         — the tournament leader after two rounds

Grading the wrong one produces a confident number about nothing. This is the same failure class as
the deadline contamination: the harness runs clean and the ANSWER is to a different question.

DISCRIMINATOR — the book priced this market knowing R1. So:
  (b) 36-hole  -> price MUST track the R1 leaderboard hard. A 65 in R1 is a large head start that
                  no amount of talent difference offsets over one round.
  (a) R2-only  -> R1 is nearly irrelevant (only through form/conditions), so the price should look
                  like a talent market — i.e. close to the 1st Round Leader price for the same
                  player, which was made BEFORE any golf was played.

Measured, with no model involved:
  corr(devigged 2RL prob, R1 score)      strongly negative => (b)
  corr(devigged 2RL prob, 1RL prob)      near 1.0          => (a)
  the implied favourite's identity: R1 leader => (b); pre-tournament favourite => (a)

Also reports the close timestamps against R1's completion, which is the temporal-integrity check:
a close stamped before R1 finished cannot be a 36-hole market priced on known R1 scores.
"""
import sqlite3
from collections import defaultdict

import numpy as np

import pga_market as PM
import pga_ruler as RU

m = sqlite3.connect("file:golf_moves.sqlite?mode=ro", uri=True, timeout=60)
rows = m.execute("SELECT event, market, runner, close_odds, close_ts FROM moves "
                 "WHERE close_odds IS NOT NULL AND event LIKE ? AND market LIKE ?%s"
                 % "", ("%St Jude%", "%Round Leader%")).fetchall()
m.close()

g = defaultdict(dict)
ts = defaultdict(list)
for ev, mk, run, od, t in rows:
    g[mk][RU.norm(run)] = float(od)
    ts[mk].append(t)
print("round-leader markets on St Jude:")
for mk in sorted(g):
    print("   %-24s runners %3d   closes %s .. %s"
          % (mk, len(g[mk]), min(ts[mk]), max(ts[mk])))

fairs = {}
for mk, q in g.items():
    f, info = PM.fair(mk, q, n_runners=len(q))
    if f:
        fairs[mk] = f
        print("   %-24s kind=%-10s overround %.3f  hold %.1f%%"
              % (mk, info["kind"], info["overround"], info["hold_pct"]))
    else:
        print("   %-24s PRICING REFUSED: %s" % (mk, info))

r = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
eid = r.execute("SELECT event_id FROM rounds WHERE event LIKE ? AND date LIKE ? LIMIT 1",
                ("%St. Jude%", "2026%")).fetchone()[0]
byp = defaultdict(dict)
for pl, rd, s in r.execute("SELECT player, rnd, score FROM rounds WHERE event_id=?", (eid,)):
    byp[RU.norm(pl)][int(rd)] = float(s)
r.close()
r1 = {p: v[1] for p, v in byp.items() if 1 in v}
r2 = {p: v[2] for p, v in byp.items() if 2 in v}
t36 = {p: v[1] + v[2] for p, v in byp.items() if 1 in v and 2 in v}
print("\nresults: R1 %d, R2 %d, 36-hole %d" % (len(r1), len(r2), len(t36)))

k2 = next((k for k in fairs if k.lower().startswith("2nd")), None)
k1 = next((k for k in fairs if k.lower().startswith("1st")), None)
if not k2:
    raise SystemExit("no priced 2nd Round Leader market")

f2 = fairs[k2]
common = [p for p in f2 if p in r1]
x = np.array([f2[p] for p in common])
y = np.array([r1[p] for p in common])
print("\n" + "=" * 78)
print("DISCRIMINATOR")
print("=" * 78)
print("   corr(2RL prob, R1 score) = %+.3f   over %d runners" % (np.corrcoef(x, y)[0, 1], len(x)))
print("      (strongly NEGATIVE => the price knows R1 => 36-HOLE market)")

if k1:
    f1 = fairs[k1]
    c = [p for p in f2 if p in f1]
    a = np.array([f1[p] for p in c]); b = np.array([f2[p] for p in c])
    print("   corr(2RL prob, 1RL prob) = %+.3f   over %d shared runners"
          % (np.corrcoef(a, b)[0, 1], len(c)))
    print("      (near 1.0 => pure talent market, R1 ignored => R2-ONLY market)")
    mv = sorted(c, key=lambda p: -(f2[p] - f1[p]))[:5]
    print("\n   biggest price GAINERS from 1RL -> 2RL (should be the R1 leaders if 36-hole):")
    for p in mv:
        print("      %-24s 1RL %.3f -> 2RL %.3f  (R1 %s)"
              % (p[:24], f1[p], f2[p], r1.get(p, "?")))

top = sorted(f2, key=lambda p: -f2[p])[:6]
print("\n   2RL favourites: " + ", ".join("%s %.3f (R1 %s)" % (p[:16], f2[p], r1.get(p, "?"))
                                          for p in top))
lo1 = min(r1.values()) if r1 else None
print("   R1 leaders (%s): %s" % (lo1, ", ".join(p[:18] for p in r1 if r1[p] == lo1)))

for lbl, d in (("lowest R2 score", r2), ("lowest 36-hole", t36)):
    if d:
        lo = min(d.values())
        print("   %-16s winner(s) @ %g: %s"
              % (lbl, lo, ", ".join(p[:18] for p in d if d[p] == lo)))
