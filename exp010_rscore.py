#!/usr/bin/env python3
"""EXP-010 — Round Score markets: an entirely untested family, gradeable NOW.

Top-N is BLOCKED until St Jude finishes Sunday. This is the highest-value unblocked market:
"X Round N Score" has tee-gated closes in golf_moves AND results in pga_model.rounds, and has
never been tested against prices. The live E3-rscore stream is 2-9 (-5.75u) in shadow, which is
suggestive but was graded at flag price, not at the close.

PRICING. These are LADDERS — "Round 2 Score" at 4 or 6 runners is 2 or 3 alternate lines
(over/under 68.5, 69.5, 70.5) pooled under ONE market name. Pooled overround reads 2.11 or 3.18,
which looks like a 52-68% hold and is really 2-3 stacked two-way books at ~1.06 each. pga_market
splits them per line; a pooled devig would price every selection at a half or a third of value.

TWO QUESTIONS, deliberately separated:
  MARKET   is the devigged close itself honest, and is either side systematically mispriced?
           (needs no model at all — this is where the birdie work found its only real structure)
  MODEL    does pga_ruler's round-score distribution beat that close?

⚠️ Grading is on the RAW round score, and the line is a stroke count, so integer lines PUSH.
Skipped and counted rather than graded as losses.
"""
import math
import re
import sqlite3
from collections import defaultdict

import numpy as np

import pga_market as PM
import pga_ruler as RU

EPS = 1e-9
m = sqlite3.connect("file:golf_moves.sqlite?mode=ro", uri=True, timeout=60)
rows = m.execute("SELECT event, market, runner, rnd, close_odds FROM moves "
                 "WHERE market LIKE ? AND close_odds IS NOT NULL",
                 ("%Round % Score%",)).fetchall()
m.close()
g, meta = defaultdict(dict), {}
for ev, mk, run, rnd, od in rows:
    k = (str(ev).strip(), mk)
    g[k][run] = float(od)
    meta[k] = (str(ev).strip(), int(rnd) if rnd else None)
print("round-score markets %d, quotes %d" % (len(g), len(rows)))

kinds = defaultdict(int)
fairs = {}
for k, q in g.items():
    f, info = PM.fair(k[1], q, n_runners=len(q))
    kinds[info.get("kind", "?")] += 1
    if f:
        fairs[k] = f
print("classified: " + " ".join("%s=%d" % kv for kv in sorted(kinds.items())))

r = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
sc, evn = {}, {}
for eid, ev, pl, rd, s in r.execute("SELECT event_id, event, player, rnd, score FROM rounds"):
    key = " ".join(str(ev).lower().split())
    sc[(key, RU.norm(pl), int(rd))] = float(s)
    evn[key] = key
r.close()
DROP = {"pga", "2026", "2025", "championship", "the", "tour", "classic", "invitational", "open"}


def match(ev):
    k = set(" ".join(str(ev).lower().split()).split()) - DROP
    best, bn = None, 0
    for nm in evn:
        ov = len(k & (set(nm.split()) - DROP))
        if ov > bn:
            best, bn = nm, ov
    return best if bn >= 1 else None


G, pushes, unres = [], 0, 0
for k, f in fairs.items():
    ev, rnd = meta[k]
    tn = match(ev)
    if tn is None or rnd is None:
        unres += 1
        continue
    for run, pf in f.items():
        mm = re.search(r"^(.*?)\s+(over|under)\s+([\d.]+)\s*$", run.strip(), re.I)
        if not mm:
            continue
        pl, side, line = mm.group(1), mm.group(2).lower(), float(mm.group(3))
        a = sc.get((tn, RU.norm(pl), rnd))
        if a is None:
            continue
        if abs(line - round(line)) < 1e-9:
            pushes += 1
            continue
        y = 1.0 if ((side == "over" and a > line) or (side == "under" and a < line)) else 0.0
        G.append(dict(ev=ev, rnd=rnd, pl=pl, side=side, line=line, od=g[k][run],
                      book=pf, y=y, act=a, cl=(ev, rnd)))
print("graded selections %d | integer-line pushes skipped %d | unmatched markets %d\n"
      % (len(G), pushes, unres))
if not G:
    raise SystemExit("nothing gradeable")

# ONE ROW PER MARKET-LINE for correlation work: over-side only (EXP-007's lesson)
OV = [x for x in G if x["side"] == "over"]

print("=" * 80)
print("MARKET — is the devigged close honest? (no model involved)")
print("=" * 80)
n = len(OV)
b = np.array([x["book"] for x in OV])
y = np.array([x["y"] for x in OV])
llb = float(-(y * np.log(np.clip(b, EPS, 1 - EPS))
              + (1 - y) * np.log(np.clip(1 - b, EPS, 1 - EPS))).mean())
by = defaultdict(list)
for x in OV:
    by[x["cl"]].append(x["y"] - x["book"])
cl = np.array([np.mean(v) for v in by.values()])
se = cl.std(ddof=1) / math.sqrt(len(cl)) if len(cl) > 1 else float("nan")
print("   over side: n=%d  book %.4f  realised %.4f  gap %+.4f  clustered SE %.4f  z=%+.2f"
      % (n, b.mean(), y.mean(), y.mean() - b.mean(), se, (y.mean() - b.mean()) / se))
print("   book log-loss %.5f" % llb)

print("\n   by line:")
bl = defaultdict(list)
for x in OV:
    bl[x["line"]].append(x)
for ln in sorted(bl):
    v = bl[ln]
    if len(v) >= 5:
        print("      over %5.1f  n=%3d  book %.3f  realised %.3f  gap %+.4f"
              % (ln, len(v), np.mean([z["book"] for z in v]),
                 np.mean([z["y"] for z in v]), np.mean([z["y"] - z["book"] for z in v])))

print("\n   by event-round:")
for c, v in sorted(by.items()):
    print("      %-30s R%s n=%2d  gap %+.4f" % (c[0][:30], c[1], len(v), np.mean(v)))

print("\n" + "=" * 80)
print("BLIND SIDE-BETTING at the close (vig inside the price)")
print("=" * 80)
for side in ("over", "under"):
    v = [x for x in G if x["side"] == side]
    if not v:
        continue
    pnl = sum((x["od"] - 1.0) if x["y"] > 0 else -1.0 for x in v)
    print("   %-6s n=%3d  hit %5.1f%%  %+7.2fu  ROI %+6.1f%%"
          % (side, len(v), 100 * np.mean([x["y"] for x in v]), pnl, 100 * pnl / len(v)))

print("\n" + "=" * 80)
print("SANITY — does the realised score distribution match what the ladder implies?")
print("=" * 80)
acts = np.array([x["act"] for x in OV])
print("   realised round scores: mean %.2f  sd %.2f  n=%d" % (acts.mean(), acts.std(), len(acts)))
print("   %d event-rounds, %d distinct players" % (len(by), len({x['pl'] for x in OV})))
