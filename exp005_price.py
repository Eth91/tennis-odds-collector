#!/usr/bin/env python3
"""EXP-005 — is the book's 4.5 under price systematically below the player's own base rate?

EXP-004: pooled, the book charges 0.5407 for under-4.5 while that population's realised P(<=4) is
0.5961 over 13,319 rounds — a ~5.5pp structural gap, i.e. ~+4% EV. But the observed +11% ROI sat
ENTIRELY in the 1.75 bucket (@1.50 -6.3%, @1.75 +31.1%, @2.00 -9.5%), which is the signature of a
small-sample accident rather than a shade.

Outcomes on n=104 are far too noisy to separate those. PRICES are not. So compare, per selection:

    book devigged P(under)   vs   that PLAYER's own historical P(<=4 birdies)

This replaces a binary outcome (variance 0.25) with a base rate estimated from dozens of rounds,
so the same 104 selections carry much more information. If the book is genuinely shading, the gap
is present per player and roughly constant across prices. If EXP-003's result was luck, the gap
collapses toward zero and only the outcomes looked good.

⚠️ LEAKAGE: a player's base rate must come from rounds OTHER than the graded one. Career-including
-the-round would let the outcome leak into its own benchmark and guarantee agreement.
⚠️ This tests the BOOK, not the model. A confirmed shade is bettable without a simulator; a
refuted one means the birdie record is riding variance.
"""
import re
import sqlite3
from collections import defaultdict

import numpy as np

import pga_market as PM
import pga_ruler as RU

MINR = 25          # a base rate on fewer rounds than this is too noisy to benchmark a price

m = sqlite3.connect("file:golf_moves.sqlite?mode=ro", uri=True, timeout=60)
rows = m.execute("SELECT event, market, runner, rnd, close_odds FROM moves "
                 "WHERE market LIKE ? AND close_odds IS NOT NULL",
                 ("%Total Birdies or Better Round%",)).fetchall()
m.close()
g, meta = defaultdict(dict), {}
for ev, mk, run, rnd, od in rows:
    k = (str(ev).strip(), mk)
    g[k][run] = float(od)
    meta[k] = (str(ev).strip(), int(rnd) if rnd else None)

r = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
act, tnames = {}, set()
allr = defaultdict(list)                     # player -> [(tname, rnd, birdies)]
for tn, pl, rd, b3, b4, b5 in r.execute(
        "SELECT tname, player, rnd, p3b, p4b, p5b FROM birdie_rounds"):
    key = " ".join(str(tn).lower().split())
    tnames.add(key)
    tot = float((b3 or 0) + (b4 or 0) + (b5 or 0))
    act[(key, RU.norm(pl), int(rd))] = tot
    allr[RU.norm(pl)].append((key, int(rd), tot))
r.close()
DROP = {"pga", "2026", "2025", "championship", "the", "tour", "classic", "invitational", "open"}


def match(ev):
    k = set(" ".join(str(ev).lower().split()).split()) - DROP
    best, bn = None, 0
    for nm in tnames:
        ov = len(k & (set(nm.split()) - DROP))
        if ov > bn:
            best, bn = nm, ov
    return best if bn >= 1 else None


recs = []
for k, q in g.items():
    f, _i = PM.fair(k[1], q, n_runners=len(q))
    if not f:
        continue
    ev, rnd = meta[k]
    tn = match(ev)
    if tn is None or rnd is None:
        continue
    for run, pf in f.items():
        mm = re.search(r"^(.*?)\s+(under)\s+([\d.]+)\s*$", run.strip(), re.I)
        if not mm:
            continue
        pl, line = mm.group(1), float(mm.group(3))
        key = RU.norm(pl)
        a = act.get((tn, key, rnd))
        if a is None or abs(line - round(line)) < 1e-9:
            continue
        # LEAVE-THIS-ROUND-OUT base rate
        others = [b for (t, rr, b) in allr.get(key, []) if not (t == tn and rr == rnd)]
        if len(others) < MINR:
            continue
        base = float(np.mean([1.0 if b < line else 0.0 for b in others]))
        recs.append(dict(pl=pl, line=line, od=q[run], book=pf, base=base,
                         n_hist=len(others), y=1.0 if a < line else 0.0, cl=(ev, rnd)))

print("selections with a leave-one-out base rate (>=%d other rounds): %d" % (MINR, len(recs)))
for line in sorted({x["line"] for x in recs}):
    v = [x for x in recs if x["line"] == line]
    if len(v) < 10:
        continue
    d = np.array([x["base"] - x["book"] for x in v])
    by = defaultdict(list)
    for x in v:
        by[x["cl"]].append(x["base"] - x["book"])
    cl = np.array([np.mean(c) for c in by.values()])
    se = cl.std(ddof=1) / np.sqrt(len(cl)) if len(cl) > 1 else float("nan")
    print("\n=== UNDER %.1f  (n=%d, %d event-rounds) ===" % (line, len(v), len(by)))
    print("   book devigged   %.4f" % np.mean([x["book"] for x in v]))
    print("   player base     %.4f   <- leave-this-round-out, mean %d prior rounds"
          % (np.mean([x["base"] for x in v]), np.mean([x["n_hist"] for x in v])))
    print("   GAP             %+.4f   clustered SE %.4f   z=%+.2f" % (d.mean(), se, d.mean() / se))
    print("   realised        %.4f" % np.mean([x["y"] for x in v]))
    print("   selections where base > book: %d of %d (%.0f%%)"
          % (sum(1 for x in v if x["base"] > x["book"]), len(v),
             100.0 * sum(1 for x in v if x["base"] > x["book"]) / len(v)))
    print("   by price bucket — a real shade should appear at EVERY price:")
    b = defaultdict(list)
    for x in v:
        b[round(x["od"] * 4) / 4].append(x)
    for od in sorted(b):
        vv = b[od]
        if len(vv) >= 5:
            print("      @%.2f n=%3d  book %.3f  base %.3f  gap %+.4f"
                  % (od, len(vv), np.mean([z["book"] for z in vv]),
                     np.mean([z["base"] for z in vv]),
                     np.mean([z["base"] - z["book"] for z in vv])))
