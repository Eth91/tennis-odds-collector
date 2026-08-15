#!/usr/bin/env python3
"""EXP-004 — is the 4.5-under edge OURS or the BOOK'S? And what is the mechanism?

EXP-003 established that blind under-betting at the 4.5 birdie line returns +12.1% at the close,
event-clustered z=+2.23, permutation p=0.0134, 5 of 6 clusters positive. No simulator was involved.

That reframes the ARMED birdie record (23-13, +8.98u, almost all 4.5 unders). Two possibilities,
and they have completely different futures:

  A  THE MODEL finds mispriced unders          -> the simulator is the asset
  B  THE BOOK shades the 4.5 over              -> the LINE is the asset, model is decoration

Charter question: "what does our model know that the market does not?" If blind betting matches
model-selected betting, the honest answer is nothing, and the edge would survive deleting the
model — which also means it survives the model being wrong.

MECHANISM CHECK. If the book is shading, the tell is in the DISTRIBUTION: P(birdies <= 4) among
players the book posts at 4.5 should exceed the price it charges. That is checkable against 34k
graded rounds without any close at all, and it is the difference between "3 lucky tournaments"
and "a structural feature of how this line is priced".

⚠️ POPULATION MATTERS. The book only posts 4.5 on players it expects near 4.5, so the base rate
must be measured on THAT population, not on all players. Using everyone would import weak players
who never make 5 birdies and manufacture the result.
"""
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
hist = defaultdict(list)                       # player -> [birdies per round, chronological]
for tn, pl, rd, b3, b4, b5 in r.execute(
        "SELECT tname, player, rnd, p3b, p4b, p5b FROM birdie_rounds"):
    key = " ".join(str(tn).lower().split())
    tnames.add(key)
    tot = float((b3 or 0) + (b4 or 0) + (b5 or 0))
    act[(key, RU.norm(pl), int(rd))] = tot
    hist[RU.norm(pl)].append(tot)
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
        G.append(dict(pl=pl, side=side, line=line, od=q[run], pf=pf, y=y, act=a,
                      cl=(ev, rnd)))

U45 = [x for x in G if x["side"] == "under" and x["line"] == 4.5]
print("under-4.5 selections: %d over %d event-rounds\n" % (U45.__len__(),
                                                           len({x['cl'] for x in U45})))

print("=" * 80)
print("MECHANISM — what the book charges vs what the distribution says")
print("=" * 80)
posted = {RU.norm(x["pl"]) for x in U45}
pool = [v for p in posted for v in hist.get(p, [])]
if pool:
    pool = np.array(pool)
    print("   players posted at 4.5: %d | their career graded rounds: %d" % (len(posted), len(pool)))
    print("   mean birdies %.3f | P(<=4) = %.4f   <- the true under-4.5 rate for THIS population"
          % (pool.mean(), float((pool <= 4).mean())))
print("   book's average price for under 4.5 (devigged): %.4f"
      % np.mean([x["pf"] for x in U45]))
print("   realised in the graded sample:                 %.4f"
      % np.mean([x["y"] for x in U45]))
print("\n   birdie distribution for this population:")
if len(pool):
    for k in range(0, 9):
        c = int((pool == k).sum())
        print("      %d birdies %6d  %5.1f%%" % (k, c, 100.0 * c / len(pool)))

print("\n" + "=" * 80)
print("A vs B — does the MODEL beat BLIND on the same selections?")
print("=" * 80)


def roi(v):
    if not v:
        return 0.0, 0.0, 0
    p = sum((x["od"] - 1.0) if x["y"] > 0 else -1.0 for x in v)
    return p, 100.0 * p / len(v), len(v)


p, rr, n = roi(U45)
print("   BLIND every under-4.5      n=%3d  %+7.2fu  ROI %+6.1f%%" % (n, p, rr))

# model view: player's own prior mean birdies (leave-this-round-out, prior rounds only)
sel = []
for x in U45:
    h = hist.get(RU.norm(x["pl"]), [])
    if len(h) >= 10:
        prior = np.mean(h)                     # career mean incl. this round -> upper bound
        if prior <= 4.5:
            sel.append(x)
p2, rr2, n2 = roi(sel)
print("   'model-ish' filter (prior mean <= 4.5)  n=%3d  %+7.2fu  ROI %+6.1f%%" % (n2, p2, rr2))
print("   ⚠️ that filter uses career mean INCLUDING the round — an optimistic UPPER bound.")
print("      If it does not beat blind even with that advantage, selection is adding nothing.")

print("\n" + "=" * 80)
print("PRICE BUCKETS — is the edge at a particular price, or everywhere?")
print("=" * 80)
b = defaultdict(list)
for x in U45:
    b[round(x["od"] * 4) / 4].append(x)
for od in sorted(b):
    p3, r3, n3 = roi(b[od])
    if n3 >= 5:
        print("   @%.2f  n=%3d  hit %5.1f%%  ROI %+6.1f%%"
              % (od, n3, 100 * np.mean([x["y"] for x in b[od]]), r3))
