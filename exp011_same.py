#!/usr/bin/env python3
"""EXP-011 — are the birdie and round-score "edges" the SAME observation?

Two apparent market findings:
    birdie UNDERS profitable   -> fewer birdies than the book priced
    round-score OVERS profitable -> higher scores than the book priced

Those are not independent. Fewer birdies IS a higher score. If both are driven by the same
event-rounds simply playing harder than the book expected, then I do not have two confirmations
of a market edge — I have ONE correlated observation across ~8 event-rounds, and the apparent
replication is an illusion.

TEST: per event-round, compute
    birdie gap      = mean(realised under) - mean(book under)      over birdie markets
    round-score gap = mean(realised over)  - mean(book over)       over round-score markets
and correlate them across the event-rounds where both exist.

    strong POSITIVE correlation -> one shared conditions effect, both "edges" are one datum,
                                   and the honest n is the number of EVENT-ROUNDS (~6-8), not
                                   the number of selections (~300).
    ~zero correlation           -> genuinely separate market structures, worth pursuing apart.

⚠️ This is the multiple-testing rule made concrete: the charter warns against treating the best
of many tested markets as an edge. Here the two markets are not even distinct draws.
"""
import re
import sqlite3
from collections import defaultdict

import numpy as np

import pga_market as PM
import pga_ruler as RU

m = sqlite3.connect("file:golf_moves.sqlite?mode=ro", uri=True, timeout=60)
allrows = m.execute("SELECT event, market, runner, rnd, close_odds FROM moves "
                    "WHERE close_odds IS NOT NULL AND (market LIKE ? OR market LIKE ?)",
                    ("%Total Birdies or Better Round%", "%Round % Score%")).fetchall()
m.close()

r = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
sc, bird, names = {}, {}, set()
for eid, ev, pl, rd, s in r.execute("SELECT event_id, event, player, rnd, score FROM rounds"):
    k = " ".join(str(ev).lower().split())
    sc[(k, RU.norm(pl), int(rd))] = float(s)
    names.add(k)
for tn, pl, rd, b3, b4, b5 in r.execute(
        "SELECT tname, player, rnd, p3b, p4b, p5b FROM birdie_rounds"):
    k = " ".join(str(tn).lower().split())
    bird[(k, RU.norm(pl), int(rd))] = float((b3 or 0) + (b4 or 0) + (b5 or 0))
    names.add(k)
r.close()
DROP = {"pga", "2026", "2025", "championship", "the", "tour", "classic", "invitational", "open"}


def match(ev):
    k = set(" ".join(str(ev).lower().split()).split()) - DROP
    best, bn = None, 0
    for nm in names:
        ov = len(k & (set(nm.split()) - DROP))
        if ov > bn:
            best, bn = nm, ov
    return best if bn >= 1 else None


g, meta = defaultdict(dict), {}
for ev, mk, run, rnd, od in allrows:
    k = (str(ev).strip(), mk)
    g[k][run] = float(od)
    meta[k] = (str(ev).strip(), int(rnd) if rnd else None, mk)

BG = defaultdict(list)      # event-round -> [realised_under - book_under]
RG = defaultdict(list)      # event-round -> [realised_over  - book_over]
FIELD = defaultdict(list)   # event-round -> realised scores, for the conditions read
for k, q in g.items():
    f, _i = PM.fair(k[1], q, n_runners=len(q))
    if not f:
        continue
    ev, rnd, mk = meta[k]
    tn = match(ev)
    if tn is None or rnd is None:
        continue
    is_bird = "Birdies" in mk
    for run, pf in f.items():
        mm = re.search(r"^(.*?)\s+(over|under)\s+([\d.]+)\s*$", run.strip(), re.I)
        if not mm:
            continue
        pl, side, line = mm.group(1), mm.group(2).lower(), float(mm.group(3))
        if abs(line - round(line)) < 1e-9:
            continue
        key = (tn, RU.norm(pl), rnd)
        a = bird.get(key) if is_bird else sc.get(key)
        if a is None:
            continue
        if is_bird and side == "under":
            BG[(ev, rnd)].append((1.0 if a < line else 0.0) - pf)
        elif (not is_bird) and side == "over":
            RG[(ev, rnd)].append((1.0 if a > line else 0.0) - pf)
            FIELD[(ev, rnd)].append(a)

both = sorted(set(BG) & set(RG))
print("event-rounds with BOTH markets: %d\n" % len(both))
print("   %-32s %4s %10s %10s %10s %6s" % ("event", "rnd", "birdie gap", "score gap",
                                           "field mean", "n"))
xs, ys = [], []
for ev, rnd in both:
    bg = float(np.mean(BG[(ev, rnd)]))
    rg = float(np.mean(RG[(ev, rnd)]))
    fm = float(np.mean(FIELD[(ev, rnd)])) if FIELD[(ev, rnd)] else float("nan")
    xs.append(bg); ys.append(rg)
    print("   %-32s R%-3s %+10.4f %+10.4f %10.2f %6d"
          % (ev[:32], rnd, bg, rg, fm, len(BG[(ev, rnd)])))

if len(xs) >= 3:
    c = float(np.corrcoef(xs, ys)[0, 1])
    print("\n" + "=" * 78)
    print("corr(birdie-under gap, round-score-over gap) = %+.3f   over %d event-rounds"
          % (c, len(xs)))
    print("=" * 78)
    if c > 0.5:
        print("   -> SAME OBSERVATION. Both 'edges' are one conditions effect: these rounds")
        print("      played harder than the book priced. The honest n is %d EVENT-ROUNDS," % len(xs))
        print("      not the ~300 selections, and the two markets are not independent")
        print("      confirmations of anything.")
    elif abs(c) < 0.3:
        print("   -> largely INDEPENDENT. The two market structures can be pursued separately.")
    else:
        print("   -> partially shared; treat any joint claim with care.")
    # does the field's own scoring explain the gaps?
    fms = [float(np.mean(FIELD[(e, r_)])) for e, r_ in both if FIELD[(e, r_)]]
    if len(fms) == len(xs):
        print("\n   corr(field mean score, birdie gap)      = %+.3f" % np.corrcoef(fms, xs)[0, 1])
        print("   corr(field mean score, round-score gap) = %+.3f" % np.corrcoef(fms, ys)[0, 1])
        print("   (positive => the harder the round actually played, the bigger the 'edge')")
