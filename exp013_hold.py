#!/usr/bin/env python3
"""EXP-013 — HOLD CENSUS. Which PGA markets could EVER pay, before any model is involved?

EXP-012's lesson made concrete. There, the model agreed with the book at corr +0.989 and the best
runner in a 68-man field was still -6.0% EV, because the market kept 26.7%. No amount of model
work reaches a price like that. Every market family we might research should therefore be screened
by its VIG FIRST, and the ones that cannot be beaten in principle should be struck off the
research programme rather than modelled and then discovered to be unbeatable one at a time.

This is entirely model-free: it reads prices and nothing else. It cannot find an edge and is not
trying to. It bounds where an edge could live.

METHOD
  group by (normalised event, market), pga_market classifies and devigs each group
  LADDERS report PER-LINE holds -- a pooled ladder overround is a meaningless number (a 3-line
    ladder at 6% each pools to ~3.2, which reads as a 68% hold no book charges)
  duplicate event-name variants folded, LATEST close per runner kept (EXP-012's snapshot trap)
  markets pga_market REFUSES are counted, never guessed at

READING THE RESULT. For a two-way price the hold is very close to the edge needed to break even,
so:
    hold < 5%       reachable -- a genuine 2-3 point model edge clears it
    hold 5-10%      marginal  -- needs an edge larger than anything demonstrated so far
    hold > 10%      unreachable in practice; strike the family
"""
import sqlite3
from collections import defaultdict

import numpy as np

import pga_market as PM
import pga_ruler as RU

m = sqlite3.connect("file:golf_moves.sqlite?mode=ro", uri=True, timeout=60)
rows = m.execute("SELECT event, market, mtype, runner, close_odds, close_ts FROM moves "
                 "WHERE close_odds IS NOT NULL").fetchall()
m.close()

# fold padded/clean event names; keep the LATEST close per (event, market, runner)
best = {}
for ev, mk, mt, run, od, ts in rows:
    evn = " ".join(str(ev).split())
    k = (evn, mk, RU.norm(run))
    if k not in best or str(ts) > best[k][0]:
        best[k] = (str(ts), float(od), mt)
print("close rows %d -> %d unique (event, market, runner)" % (len(rows), len(best)))

g, mts = defaultdict(dict), {}
for (evn, mk, run), (_ts, od, mt) in best.items():
    g[(evn, mk)][run] = od
    mts[(evn, mk)] = mt
print("market instances: %d across %d events\n" % (len(g), len({k[0] for k in g})))

fam = defaultdict(list)          # mtype -> [hold_pct, ...] one entry per priced book
refused = defaultdict(int)
kinds = defaultdict(lambda: defaultdict(int))
for k, q in g.items():
    mt = mts[k] or "?"
    f, info = PM.fair(k[1], q, n_runners=len(q))
    if not f:
        refused[mt] += 1
        continue
    kind = info.get("kind", "?")
    kinds[mt][kind] += 1
    if kind == PM.LADDER:
        for _ln, ov in info["overround_per_line"].items():
            if ov and ov > 1.0:
                fam[mt].append(100.0 * (ov - 1.0) / ov)
    else:
        fam[mt].append(info["hold_pct"])

print("=" * 92)
print("HOLD BY MARKET FAMILY — model-free")
print("=" * 92)
print("%-34s %6s %8s %8s %8s %8s  %s" % ("mtype", "books", "median", "min", "max", "refused",
                                         "verdict"))
out = []
for mt in sorted(fam, key=lambda x: np.median(fam[x])):
    v = np.array(fam[mt])
    med = float(np.median(v))
    verdict = ("REACHABLE" if med < 5 else "marginal" if med < 10 else "UNREACHABLE")
    out.append((mt, len(v), med, float(v.min()), float(v.max()), refused.get(mt, 0), verdict))
    print("%-34s %6d %7.1f%% %7.1f%% %7.1f%% %8d  %s"
          % (mt[:34], len(v), med, v.min(), v.max(), refused.get(mt, 0), verdict))

only_ref = sorted(set(refused) - set(fam))
if only_ref:
    print("\nfamilies pga_market REFUSED entirely (unclassifiable, never guessed):")
    for mt in only_ref:
        print("   %-40s %d books" % (mt[:40], refused[mt]))

print("\n" + "=" * 92)
print("WHERE RESEARCH CAN POSSIBLY PAY")
print("=" * 92)
reach = [o for o in out if o[6] == "REACHABLE"]
marg = [o for o in out if o[6] == "marginal"]
unre = [o for o in out if o[6] == "UNREACHABLE"]
for lbl, grp in (("REACHABLE (hold < 5%)", reach), ("MARGINAL (5-10%)", marg),
                 ("UNREACHABLE (>10%) — strike these", unre)):
    print("\n   %s" % lbl)
    if not grp:
        print("      (none)")
    for mt, n, med, lo, hi, _r, _v in grp:
        print("      %-36s median %5.1f%%  (%d books, best %.1f%%)" % (mt[:36], med, n, lo))

tot = sum(o[1] for o in out)
print("\n   %d priced books total: %d reachable, %d marginal, %d unreachable"
      % (tot, sum(o[1] for o in reach), sum(o[1] for o in marg), sum(o[1] for o in unre)))
print("   kinds seen per family:")
for mt in sorted(kinds):
    print("      %-36s %s" % (mt[:36], dict(kinds[mt])))

# THE BLIND SPOT. A family with rows but ZERO closes is not a family without vig -- it is one the
# tee gate could not resolve a deadline for, so it fails closed and we have never seen its price.
# 3-balls are among the tightest products in golf; being blind to them is an infrastructure gap,
# not evidence about them. tee_why carries the gate's own reason.
print("\n" + "=" * 92)
print("BLIND SPOT — families with rows but NO closes (never priced, not 'no edge')")
print("=" * 92)
m2 = sqlite3.connect("file:golf_moves.sqlite?mode=ro", uri=True, timeout=60)
zero = m2.execute(
    "SELECT mtype, COUNT(*) n, COUNT(DISTINCT event) ev, COUNT(close_odds) nc "
    "FROM moves GROUP BY mtype HAVING nc=0 AND n>=50 ORDER BY n DESC").fetchall()
print("%-36s %8s %6s   %s" % ("mtype", "rows", "events", "gate reason (tee_why)"))
for mt, n, ev, _nc in zero:
    why = m2.execute("SELECT tee_why, COUNT(*) c FROM moves WHERE mtype=? "
                     "GROUP BY tee_why ORDER BY c DESC LIMIT 2", (mt,)).fetchall()
    print("%-36s %8d %6d   %s" % (str(mt)[:36], n, ev,
                                  "; ".join("%s x%d" % (w or "NULL", c) for w, c in why)))
print("\n   %d rows in families we have never priced." % sum(z[1] for z in zero))
m2.close()
