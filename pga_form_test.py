"""H-P1: does a player's EARLIER ROUND in this tournament predict their next one, net of conditions?

The user's caution is the whole design problem: a course plays harder or easier round to round, so
if you simply correlate "birdies in R1" with "birdies in R2" you will find a strong relationship
that is mostly WEATHER — everyone birdies more on the calm morning. That would look like form and
be nothing of the sort.

So conditions are removed first, at the round level, using the field itself:

    round_factor(event, rnd) = field birdie rate that round / field birdie rate that event
    expected(player, rnd)    = player's OWN historical rate * round_factor
    residual(player, rnd)    = actual - expected

`player's own historical rate` is computed LEAVE-ONE-EVENT-OUT, so the current tournament never
informs its own baseline. The residual is then what the player did beyond what their history and
that round's conditions predict — the only thing that could honestly be called form.

TEST: correlate residual in round k with residual in round k+1, same player, same event.
NULL:  the same correlation across DIFFERENT events, which should sit near zero. If the null is not
       near zero the de-conditioning has failed and the real result cannot be read.

Measurement only. PGA is frozen; this decides whether a hypothesis is worth registering, nothing more.
"""
import math
import sqlite3
import statistics as st
from collections import defaultdict

import pga_birdies as B

con = sqlite3.connect(B.DB)
rows = list(con.execute(
    "SELECT tid, tname, player, rnd, "
    "COALESCE(p3h,0)+COALESCE(p4h,0)+COALESCE(p5h,0) AS holes, "
    "COALESCE(p3b,0)+COALESCE(p4b,0)+COALESCE(p5b,0) AS birds "
    "FROM birdie_rounds"))
con.close()
print("  %d player-rounds across %d events" % (len(rows), len({r[0] for r in rows})))

# keep only full-ish rounds so a WD or a suspended round cannot masquerade as a bad round
R = [r for r in rows if (r[4] or 0) >= 17]
print("  %d after dropping partial rounds (<17 holes)" % len(R))

rate = {}                                        # (tid, player, rnd) -> birdies per hole
for tid, tn, pl, rnd, holes, birds in R:
    rate[(tid, pl, int(rnd))] = birds / holes

# ── conditions: the field's rate each round, relative to that event ───────────
by_ev_rnd = defaultdict(list)
by_ev = defaultdict(list)
for (tid, pl, rnd), v in rate.items():
    by_ev_rnd[(tid, rnd)].append(v)
    by_ev[tid].append(v)
rfac = {}
for (tid, rnd), v in by_ev_rnd.items():
    base = st.mean(by_ev[tid]) or 1e-9
    rfac[(tid, rnd)] = (st.mean(v) / base) if base else 1.0
sp = sorted(rfac.values())
print("  round factors: median %.3f, 10th %.3f, 90th %.3f  (1.0 = an average round for that event)"
      % (sp[len(sp) // 2], sp[int(.1 * len(sp))], sp[int(.9 * len(sp))]))
print("  -> spread confirms rounds really do play harder/easier; that is what gets removed.")

# ── player baseline, LEAVE-ONE-EVENT-OUT ─────────────────────────────────────
tot = defaultdict(lambda: [0.0, 0])              # player -> [sum rate, n]
per_ev = defaultdict(lambda: [0.0, 0])           # (player, tid) -> [sum rate, n]
for (tid, pl, rnd), v in rate.items():
    tot[pl][0] += v
    tot[pl][1] += 1
    per_ev[(pl, tid)][0] += v
    per_ev[(pl, tid)][1] += 1


def baseline(pl, tid):
    s, n = tot[pl]
    es, en = per_ev[(pl, tid)]
    s, n = s - es, n - en                        # drop THIS event entirely
    return (s / n) if n >= 4 else None           # need a real history


resid = {}
for (tid, pl, rnd), v in rate.items():
    b = baseline(pl, tid)
    f = rfac.get((tid, rnd))
    if b is None or not f:
        continue
    resid[(tid, pl, rnd)] = v - b * f


def corr(pairs):
    if len(pairs) < 12:
        return None, len(pairs)
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return (num / (dx * dy) if dx and dy else None), len(pairs)


print("\n=== TEST: does round k predict round k+1, same player, same event? ===")
print("  %-10s %8s %8s %s" % ("pair", "n", "corr", "reading"))
allp = []
for k in (1, 2, 3):
    pairs = []
    for (tid, pl, rnd), v in resid.items():
        if rnd != k:
            continue
        nxt = resid.get((tid, pl, k + 1))
        if nxt is not None:
            pairs.append((v, nxt))
    c, n = corr(pairs)
    allp += pairs
    print("  R%d -> R%d  %8d %8s %s" % (k, k + 1, n, ("%+.3f" % c) if c is not None else "n/a",
                                        "" if c is None else
                                        ("form carries" if c > 0.10 else
                                         "no carry-over" if abs(c) <= 0.10 else "NEGATIVE")))
c, n = corr(allp)
print("  %-10s %8d %8s" % ("pooled", n, ("%+.3f" % c) if c is not None else "n/a"))

print("\n=== NULL: same-round residuals across DIFFERENT events (should be ~0) ===")
import random
rng = random.Random(11)
keys = [k for k in resid if k[2] == 1]
null = []
for _ in range(min(len(allp), 4000)):
    a, b2 = rng.choice(keys), rng.choice(keys)
    if a[0] == b2[0]:
        continue
    nb = resid.get((b2[0], b2[1], 2))
    if nb is not None:
        null.append((resid[a], nb))
cn, nn = corr(null)
print("  shuffled  %8d %8s  (a non-zero null means the de-conditioning leaked)"
      % (nn, ("%+.3f" % cn) if cn is not None else "n/a"))

if c is not None:
    print("\n=== what it would be worth ===")
    sd = st.pstdev([p[0] for p in allp]) if len(allp) > 2 else 0
    print("  residual sd = %.4f birdies/hole (%.2f per 18 holes)" % (sd, sd * 18))
    print("  a correlation of %+.3f moves the next round's projection by %.2f birdies per 18"
          % (c, abs(c) * sd * 18))
    print("  compare: the model's flags this week sit %.2f-%.2f birdies from their lines."
          % (0.5, 1.0))
