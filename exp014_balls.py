#!/usr/bin/env python3
"""EXP-014 — 2-BALLS: the first look at a family we have never once priced.

EXP-013's hold census found NO family under a 5% hold: the four tightest were PLAYER_ROUND_SCORE
5.2%, matchbets 5.3%, birdies 5.7%, and everything field-wide was 11-36%. All four have already
been tested and none produced an edge. It also found 17,257 rows in families with ZERO closes,
of which 2-/3-balls were the interesting ones: golf's tightest product, never observed, blocked
only because pga_tee_gate had no branch for them. That branch now exists (70 new resolutions,
0 changed, 0 lost).

This does NOT wait for the moves backfill. A close is by definition the last price before the
deadline, and both halves of that are already in hand -- golf_lines has every snapshot, the gate
now returns the deadline -- so the closes are reconstructed here directly.

TWO QUESTIONS, in the order that matters:
  1. HOLD. Model-free. If 2-balls price like the other families (5%+) they are one more marginal
     market and the answer is already known. If they are genuinely tight, this is the first
     reachable family found and it changes what is worth researching.
  2. EDGE. Only if the hold justifies asking. pga_ruler.matchup_prob is the model's own head-to-
     head number and has never been scored against a real two-ball price.

SETTLEMENT: lowest score in the named round. Two runners and no tie selection, so a TIE IS A PUSH
-- stake returned, not a loss. Ties are counted and excluded, never graded as losses; golf rounds
tie constantly and grading them as losses would manufacture a large fake book edge.

TEMPORAL INTEGRITY: ratings are fit as-of the round's own date, so they see only rounds strictly
before it, and the price used is the last one stamped before that group's earliest tee.
"""
import datetime as dt
import math
import re
import sqlite3
from collections import defaultdict

import numpy as np

import pga_market as PM
import pga_ruler as RU
import pga_tee_gate as TG

EPS = 1e-9

L = sqlite3.connect("file:golf_lines.sqlite?mode=ro", uri=True, timeout=120)
rows = L.execute("""SELECT event, market, runner, odds, collected_at, mtype FROM golf_lines
                    WHERE mtype IN ('2_BALLS_IMG','3_BALLS_IMG')""").fetchall()
print("raw ball price rows: %d" % len(rows))

# last price per (event, market, runner) at or before that market's deadline
dl_cache, last = {}, {}
skipped = defaultdict(int)
for ev, mk, run, od, ts, mt in rows:
    key = (ev, mk)
    if key not in dl_cache:
        dl_cache[key] = TG.deadline(ev, mk)
    d, why = dl_cache[key]
    if d is None:
        skipped[why.split(":")[0]] += 1
        continue
    if dt.datetime.fromisoformat(str(ts)) > d:
        continue                                   # in-play, never a close
    k = (ev, mk, RU.norm(run))
    if k not in last or str(ts) > last[k][0]:
        # keep the RAW spelling too: pga_ruler's ratings are keyed by proper-case full names,
        # so a normalised key does not look up and matchup_prob would silently return nothing.
        last[k] = (str(ts), float(od), mt, str(run))
L.close()
print("unresolved rows dropped: %s" % dict(skipped))

books = defaultdict(dict)
meta = {}
raw = {}
for (ev, mk, run), (ts, od, mt, rawname) in last.items():
    books[(ev, mk)][run] = od
    raw[run] = rawname
    meta[(ev, mk)] = (mt, ts)
print("reconstructed ball books: %d\n" % len(books))

print("=" * 88)
print("Q1 — HOLD (model-free). Is this family reachable at all?")
print("=" * 88)
holds = defaultdict(list)
fairs = {}
refuse = defaultdict(int)
for k, q in books.items():
    f, info = PM.fair(k[1], q, n_runners=len(q))
    if not f:
        # LOUD. A silent skip here is how 67 refused books read as an empty hold table.
        refuse["%s: %s" % (info.get("kind"), info.get("why"))] += 1
        continue
    fairs[k] = f
    holds[meta[k][0]].append(info["hold_pct"])
if refuse:
    print("   REFUSED books (not skipped silently):")
    for w, c in sorted(refuse.items(), key=lambda x: -x[1]):
        print("      %4d  %s" % (c, w))
for mt, v in sorted(holds.items()):
    a = np.array(v)
    print("   %-14s books %4d   median %5.2f%%   min %5.2f%%   max %5.2f%%   mean %5.2f%%"
          % (mt, len(a), np.median(a), a.min(), a.max(), a.mean()))
allh = np.concatenate([np.array(v) for v in holds.values()]) if holds else np.array([])
if allh.size:
    med = float(np.median(allh))
    print("\n   VERDICT: median hold %.2f%% -> %s" % (
        med, "REACHABLE (<5%) — first family found under the bar" if med < 5
        else "marginal (5-10%) — same neighbourhood as everything else" if med < 10
        else "UNREACHABLE (>10%)"))
    print("   for comparison (EXP-013): round score 5.2%, matchbets 5.3%, birdies 5.7%,"
          " top-20 11.2%, round leader 26.7%")

# ---------------------------------------------------------------- grade
r = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
sc, dates = {}, {}
for eid, evn, pl, rd, s, d in r.execute(
        "SELECT event_id, event, player, rnd, score, date FROM rounds"):
    k = " ".join(str(evn).lower().split())
    sc[(k, RU.norm(pl), int(rd))] = float(s)
    dates[k] = str(d)[:10]
r.close()
DROP = {"pga", "dpw", "tour", "2026", "2025", "championship", "the", "classic", "invitational",
        "open", "golf"}


def match(ev):
    k = set(" ".join(str(ev).lower().split()).split()) - DROP
    best, bn = None, 0
    for nm in dates:
        ov = len(k & (set(nm.split()) - DROP))
        if ov > bn:
            best, bn = nm, ov
    return best if bn >= 1 else None


G, ties, nores = [], 0, 0
for k, f in fairs.items():
    ev, mk = k
    tn = match(ev)
    g = re.search(r"Round (\d)", str(mk))
    if tn is None or not g:
        nores += 1
        continue
    rnd = int(g.group(1))
    runs = list(f)
    if len(runs) != 2:
        continue
    a, b = runs
    sa, sb = sc.get((tn, a, rnd)), sc.get((tn, b, rnd))
    if sa is None or sb is None:
        nores += 1
        continue
    if sa == sb:
        ties += 1
        continue
    G.append(dict(ev=ev, tn=tn, rnd=rnd, a=a, b=b, pa=f[a], pb=f[b],
                  oa=books[k][a], ob=books[k][b], ya=1.0 if sa < sb else 0.0))
print("\ngradeable 2-balls %d | ties PUSHED (excluded) %d | unresolved %d"
      % (len(G), ties, nores))
if not G:
    raise SystemExit("nothing gradeable yet")

print("\n" + "=" * 88)
print("Q2 — is the BOOK honest, and does the MODEL beat it?")
print("=" * 88)
p = np.array([x["pa"] for x in G])
y = np.array([x["ya"] for x in G])
llb = float(-(y * np.log(np.clip(p, EPS, 1)) + (1 - y) * np.log(np.clip(1 - p, EPS, 1))).mean())
byev = defaultdict(list)
for x in G:
    byev[(x["ev"], x["rnd"])].append(x["ya"] - x["pa"])
cl = np.array([np.mean(v) for v in byev.values()])
se = cl.std(ddof=1) / math.sqrt(len(cl)) if len(cl) > 1 else float("nan")
print("   book: n=%d  mean p %.4f  realised %.4f  gap %+.4f  clustered SE %.4f (%d event-rounds)"
      % (len(G), p.mean(), y.mean(), y.mean() - p.mean(), se, len(cl)))
print("   book log-loss %.5f  (0.6931 = a coin flip)" % llb)

fits, llm, nm = {}, 0.0, 0
mrows = []
errs = defaultdict(int)
for x in G:
    d = dates.get(x["tn"])
    if d not in fits:
        try:
            f_ = RU.fit(asof=d)
            # fit() returns (ratings, diagnostics); passing the TUPLE straight into
            # matchup_prob is why every probability came back missing the first time.
            fits[d] = f_[0] if isinstance(f_, tuple) else f_
        except Exception as e:                                          # noqa: BLE001
            errs["fit %s: %s" % (d, type(e).__name__)] += 1
            fits[d] = None
    R = fits[d]
    if not R:
        continue
    try:
        pm = RU.matchup_prob(R, raw.get(x["a"], x["a"]), raw.get(x["b"], x["b"]), rounds=1)
    except Exception as e:                                              # noqa: BLE001
        errs["matchup %s" % type(e).__name__] += 1
        pm = None
    if pm is None or not (0 < pm < 1):
        errs["prob unusable (%s)" % ("None" if pm is None else "%.3f" % pm)] += 1
        continue
    llm += -(x["ya"] * math.log(max(pm, EPS)) + (1 - x["ya"]) * math.log(max(1 - pm, EPS)))
    mrows.append((pm, x["pa"], x["ya"], x["oa"], x["ob"]))
    nm += 1
if nm:
    pm = np.array([m[0] for m in mrows]); pbk = np.array([m[1] for m in mrows])
    yy = np.array([m[2] for m in mrows])
    lb2 = float(-(yy * np.log(np.clip(pbk, EPS, 1))
                  + (1 - yy) * np.log(np.clip(1 - pbk, EPS, 1))).mean())
    print("\n   model: n=%d  log-loss %.5f  vs book %.5f  gap %+.2f pts -> %s"
          % (nm, llm / nm, lb2, (llm / nm - lb2) * 100,
             "MODEL BETTER" if llm / nm < lb2 else "BOOK BETTER"))
    print("   corr(model, book) = %+.3f   mean |model-book| = %.4f"
          % (float(np.corrcoef(pm, pbk)[0, 1]), float(np.abs(pm - pbk).mean())))
    dis = pm - pbk
    if len(dis) > 3:
        print("   corr(model-book disagreement, outcome) = %+.3f  <- the only thing that pays"
              % float(np.corrcoef(dis, yy)[0, 1]))
    for thr in (0.02, 0.03, 0.05):
        pnl = n_ = 0
        for q, _pb, yv, oa, ob in mrows:
            if q * oa - 1 >= thr:
                n_ += 1; pnl += (oa - 1) if yv > 0 else -1
            elif (1 - q) * ob - 1 >= thr:
                n_ += 1; pnl += (ob - 1) if yv < 1 else -1
        print("   EV>=%2.0f%%: n=%3d  %+7.2fu  ROI %+6.1f%%"
              % (100 * thr, n_, pnl, 100 * pnl / n_ if n_ else 0))
else:
    print("\n   model: no matchup probabilities available")
if errs:
    print("\n   model failures (reported, not swallowed):")
    for w, c in sorted(errs.items(), key=lambda z: -z[1])[:6]:
        print("      %4d  %s" % (c, w))
