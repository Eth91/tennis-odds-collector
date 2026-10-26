#!/usr/bin/env python3
"""EXP-003 — audit the 4.5-under signal before believing any of it.

EXP-002 found birdie UNDERS at the 4.5 line hitting 63.5% against a devigged close of 54.1%
(+9.4pp, n=104), and blind under-betting returning +8.0% ROI at the close. That is exactly the
population the live ARMED record already bets, so a false positive here is expensive.

Charter positive-result protocol. Every check below can kill it:

 1. EVENT CLUSTERING — 104 selections come from 4 tournaments. Rounds inside one event share
    course, weather and pin positions, so a naive binomial SE is badly anti-conservative. The
    honest unit is the EVENT-ROUND.
 2. IS IT JUST THE 4.5 LINE, OR ALL LINES? A general "unders are cheap" story predicts a gap at
    3.5 too. 3.5 shows +0.7pp. Concentration at one line is either a real book-shading mechanism
    or a small-sample accident.
 3. DOES EVERY EVENT AGREE? One tournament carrying the whole effect is not an edge.
 4. PERMUTATION — shuffle the over/under LABEL within each market. The observed asymmetry must
    sit outside the permuted distribution or it is noise with a story attached.
 5. VIG REALITY — the strategy pays the offered price, not the fair one. ROI is computed at the
    actual close, so the 5.7% hold is already inside the number.
"""
import math
import re
import sqlite3
from collections import defaultdict

import numpy as np

import pga_market as PM
import pga_ruler as RU

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
for tn, pl, rd, b3, b4, b5 in r.execute(
        "SELECT tname, player, rnd, p3b, p4b, p5b FROM birdie_rounds"):
    key = " ".join(str(tn).lower().split())
    tnames.add(key)
    act[(key, RU.norm(pl), int(rd))] = float((b3 or 0) + (b4 or 0) + (b5 or 0))
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


G = []
for k, q in g.items():
    f, _i = PM.fair(k[1], q, n_runners=len(q))
    if not f:
        continue
    ev, rnd = meta[k]
    tn = match(ev)
    if tn is None or rnd is None:
        continue
    for run, pf in f.items():
        mm = re.search(r"^(.*?)\s+(over|under)\s+([\d.]+)\s*$", run.strip(), re.I)
        if not mm:
            continue
        pl, side, line = mm.group(1), mm.group(2).lower(), float(mm.group(3))
        a = act.get((tn, RU.norm(pl), rnd))
        if a is None or abs(line - round(line)) < 1e-9:
            continue
        y = 1.0 if ((side == "over" and a > line) or (side == "under" and a < line)) else 0.0
        G.append(dict(ev=ev, rnd=rnd, pl=pl, side=side, line=line, od=q[run], pf=pf, y=y,
                      cl=(ev, rnd), mk=k))
print("graded %d selections, %d event-rounds\n" % (len(G), len({x["cl"] for x in G})))

U = [x for x in G if x["side"] == "under"]
U45 = [x for x in U if x["line"] == 4.5]


def roi(v):
    if not v:
        return 0.0, 0.0, 0
    pnl = sum((x["od"] - 1.0) if x["y"] > 0 else -1.0 for x in v)
    return pnl, 100.0 * pnl / len(v), len(v)


print("=" * 78)
print("1. EVENT-ROUND CLUSTERED SE (the honest unit — not the selection)")
print("=" * 78)
for lbl, v in (("all unders", U), ("unders @4.5", U45)):
    by = defaultdict(list)
    for x in v:
        by[x["cl"]].append((x["y"], x["pf"]))
    diffs = [np.mean([a - b for a, b in c]) for c in by.values() if len(c) >= 3]
    if len(diffs) < 2:
        continue
    d = np.array(diffs)
    se = d.std(ddof=1) / math.sqrt(len(d))
    print("   %-12s n_sel=%3d  clusters=%d  mean gap %+.4f  clustered SE %.4f  z=%+.2f"
          % (lbl, len(v), len(d), d.mean(), se, d.mean() / se if se > 0 else float("nan")))

print("\n" + "=" * 78)
print("2. BY LINE — a general 'unders are cheap' story predicts a gap at EVERY line")
print("=" * 78)
byl = defaultdict(list)
for x in U:
    byl[x["line"]].append(x)
for ln in sorted(byl):
    v = byl[ln]
    gap = np.mean([x["y"] - x["pf"] for x in v])
    p, rr, n = roi(v)
    print("   under %4.1f  n=%3d  gap %+.4f  %+7.2fu  ROI %+6.1f%%" % (ln, n, gap, p, rr))

print("\n" + "=" * 78)
print("3. BY EVENT-ROUND — does every cluster agree, or is one carrying it?")
print("=" * 78)
by = defaultdict(list)
for x in U45:
    by[x["cl"]].append(x)
agree = 0
for cl, v in sorted(by.items()):
    gap = np.mean([x["y"] - x["pf"] for x in v])
    p, rr, n = roi(v)
    agree += (gap > 0)
    print("   %-30s R%s n=%2d  gap %+.4f  ROI %+6.1f%%" % (cl[0][:30], cl[1], n, gap, rr))
print("   clusters with a POSITIVE gap: %d of %d" % (agree, len(by)))

print("\n" + "=" * 78)
print("4. PERMUTATION — shuffle the over/under label inside each market, 5000 draws")
print("=" * 78)
rng = np.random.default_rng(17)
obs = np.mean([x["y"] - x["pf"] for x in U45])
bym = defaultdict(list)
for x in G:
    if x["line"] == 4.5:
        bym[(x["mk"], x["line"])].append(x)
null = []
for _ in range(5000):
    tot, cnt = 0.0, 0
    for _k, pair in bym.items():
        if len(pair) != 2:
            continue
        a, b = pair
        pick = a if rng.random() < 0.5 else b
        tot += pick["y"] - pick["pf"]
        cnt += 1
    if cnt:
        null.append(tot / cnt)
null = np.array(null)
pv = float((null >= obs).mean())
print("   observed under-4.5 gap %+.4f | null mean %+.4f sd %.4f | p = %.4f"
      % (obs, null.mean(), null.std(), pv))
print("   %s" % ("SURVIVES the permutation" if pv < 0.05 else
                 "DOES NOT survive — consistent with noise"))

print("\n" + "=" * 78)
print("5. ROI AT THE OFFERED PRICE (vig already inside)")
print("=" * 78)
for lbl, v in (("all unders", U), ("unders @4.5", U45), ("unders @3.5", byl.get(3.5, []))):
    p, rr, n = roi(v)
    print("   %-14s n=%3d  %+7.2fu  ROI %+6.1f%%" % (lbl, n, p, rr))
