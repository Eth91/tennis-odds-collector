#!/usr/bin/env python3
"""EXP-002 — the ARMED birdie stream against real closes. Market-relative, not price-of-record.

Birdies is the only ARMED market and the only one with a betting record (pre-tee 23-13, +8.98u).
That record was graded at whatever price we flagged, never against the CLOSE, so it has never been
asked the question that decides edge: does the model beat the devigged closing price?

Now answerable: 380 tee-gated birdie closes over 4 events / 7 rounds, graded from birdie_rounds.

PRICING via pga_market: "X Total Birdies or Better Round N" is TWO-WAY at 2 runners (~5.7% hold)
and a LADDER at 4/6 (alternate lines pooled under one market name — devigging that as one market
would price every selection at a half or a third of its value). Unclassifiable markets are refused.

GRADING: total birdies = p3b + p4b + p5b, the same aggregation pga_birdies.py:233 uses, so this
cannot drift from the live model. Integer lines are skipped — they can push, and grading a push
as a loss would quietly bias the book's measured accuracy.
"""
import math
import re
import sqlite3
from collections import defaultdict

import pga_market as PM
import pga_ruler as RU

EPS = 1e-9

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
print("markets %d  quotes %d" % (len(g), len(rows)))

fairs, kinds = {}, defaultdict(int)
for k, q in g.items():
    f, info = PM.fair(k[1], q, n_runners=len(q))
    kinds[info.get("kind", "?")] += 1
    if f:
        fairs[k] = f
print("classified: " + " ".join("%s=%d" % kv for kv in sorted(kinds.items())))

r = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
act, tnames = {}, set()
for tn, pl, rd, b3, b4, b5 in r.execute(
        "SELECT tname, player, rnd, p3b, p4b, p5b FROM birdie_rounds"):
    key = " ".join(str(tn).lower().split())
    tnames.add(key)
    act[(key, RU.norm(pl), int(rd))] = float((b3 or 0) + (b4 or 0) + (b5 or 0))
r.close()
print("graded birdie-rounds %d over %d tournaments" % (len(act), len(tnames)))

DROP = {"pga", "2026", "2025", "championship", "the", "tour", "classic", "invitational", "open"}


def match_tname(evname):
    k = set(" ".join(str(evname).lower().split()).split()) - DROP
    best, bn = None, 0
    for name in tnames:
        ov = len(k & (set(name.split()) - DROP))
        if ov > bn:
            best, bn = name, ov
    return best if bn >= 1 else None


graded, unmatched = [], set()
for k, f in fairs.items():
    ev, rnd = meta[k]
    tn = match_tname(ev)
    if tn is None or rnd is None:
        unmatched.add(ev)
        continue
    for run, pf in f.items():
        mm = re.search(r"^(.*?)\s+(over|under)\s+([\d.]+)\s*$", run.strip(), re.I)
        if not mm:
            continue
        player, side, line = mm.group(1), mm.group(2).lower(), float(mm.group(3))
        a = act.get((tn, RU.norm(player), rnd))
        if a is None:
            continue
        if abs(line - round(line)) < 1e-9:
            continue
        y = 1.0 if ((side == "over" and a > line) or (side == "under" and a < line)) else 0.0
        graded.append((ev, rnd, player, side, line, g[k][run], pf, y, a))

if unmatched:
    print("unmatched events: %s" % sorted(unmatched))
print("\ngradeable selections: %d" % len(graded))
if not graded:
    raise SystemExit("nothing gradeable")

n = len(graded)
pf_mean = sum(x[6] for x in graded) / n
y_mean = sum(x[7] for x in graded) / n
ll_b = sum(-(x[7] * math.log(max(x[6], EPS)) + (1 - x[7]) * math.log(max(1 - x[6], EPS)))
           for x in graded) / n
print("\n=== IS THE DEVIGGED CLOSE HONEST? (validates the pricing layer on real outcomes) ===")
print("   book fair %.4f   realised %.4f   gap %+.4f   book LL %.5f   n=%d"
      % (pf_mean, y_mean, y_mean - pf_mean, ll_b, n))

print("\n=== BY EVENT / ROUND ===")
agg = defaultdict(lambda: [0, 0.0, 0.0])
for ev, rnd, _p, _s, _l, _od, pf, y, _a in graded:
    a = agg[(ev[:30], rnd)]
    a[0] += 1; a[1] += pf; a[2] += y
for (ev, rnd), (c, sp, sy) in sorted(agg.items()):
    print("   %-32s R%s n=%3d  book %.3f  actual %.3f  gap %+.3f"
          % (ev, rnd, c, sp / c, sy / c, (sy - sp) / c))

print("\n=== BY SIDE / LINE (the live record is almost all 4.5 unders) ===")
sl = defaultdict(lambda: [0, 0.0, 0.0])
for _e, _r, _p, side, line, _od, pf, y, _a in graded:
    a = sl[(side, line)]
    a[0] += 1; a[1] += pf; a[2] += y
for (side, line), (c, sp, sy) in sorted(sl.items(), key=lambda x: -x[1][0])[:12]:
    print("   %-6s %4.1f n=%3d  book %.3f  actual %.3f  gap %+.3f"
          % (side, line, c, sp / c, sy / c, (sy - sp) / c))

print("\n=== BETTING THE BOOK BLIND (no model): is either side mispriced at the close? ===")
for side in ("over", "under"):
    v = [x for x in graded if x[3] == side]
    if not v:
        continue
    stake = len(v)
    pnl = sum((x[5] - 1.0) if x[7] > 0 else -1.0 for x in v)
    print("   %-6s n=%3d  hit %5.1f%%  %+7.2fu  ROI %+6.1f%%"
          % (side, stake, 100 * sum(x[7] for x in v) / stake, pnl, 100 * pnl / stake))
print("\n⚠️ 4 events. Structural read only — not an edge claim.")
