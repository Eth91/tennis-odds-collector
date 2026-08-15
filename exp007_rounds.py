#!/usr/bin/env python3
"""EXP-007 — does the model's disagreement with the book get SHARPER in later rounds?

The strongest model result all session is conditional: win Brier skill rises 0.033 -> 0.404 by
after-R3, and the 54-hole leader converts 44.2% against a model saying 43.9%. The charter's
question is whether the sportsbook is equally efficient once that information exists.

EXP-006 answered it for round 1: corr(model-minus-book, outcome) = -0.032. No edge. But an R1
birdie market is priced when the model knows NOTHING about the event — no course read from live
scoring, no conditions, no form-in-tournament. By R3/R4 the model has 2-3 completed rounds.

So split the SAME birdie population by round and ask whether disagreement predicts better late:

    R1 markets   St Jude R1, Wyndham R1        model has no event information
    R3/R4        Wyndham R3, Wyndham R4, Rocket R4   model has 2-3 rounds of it

⚠️ IF THE LATE SPLIT ALSO SHOWS ZERO, that is the more valuable result: it would mean the book
absorbs completed-round information as fast as the model does, and the in-play skill jump is
purely uncertainty collapsing rather than an information advantage. That is the difference
between a bettable edge and a statistic.

⚠️ n per cell is small (~50-125). This can support "no signal" far better than it can support a
positive, and any positive here needs the EXP-003 audit battery before it means anything.
"""
import re
import sqlite3
from collections import defaultdict

import numpy as np

import pga_birdies as PB
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
act, tnames, allr = {}, set(), defaultdict(list)
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


rates, _f = PB.rates()
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
        # OVER side only: one row per market. Both sides is the same observation twice.
        mm = re.search(r"^(.*?)\s+(over)\s+([\d.]+)\s*$", run.strip(), re.I)
        if not mm:
            continue
        pl, side, line = mm.group(1), mm.group(2).lower(), float(mm.group(3))
        key = RU.norm(pl)
        a = act.get((tn, key, rnd))
        if a is None or abs(line - round(line)) < 1e-9:
            continue
        pr = rates.get(key) or rates.get(pl)
        if not pr:
            continue
        try:
            p_over = float(PB.p_x_or_more(pr, int(line + 0.5)))
        except Exception:                                                  # noqa: BLE001
            continue
        pm = p_over if side == "over" else 1.0 - p_over
        y = 1.0 if ((side == "over" and a > line) or (side == "under" and a < line)) else 0.0
        recs.append(dict(ev=ev, rnd=rnd, side=side, line=line, od=q[run],
                         book=pf, model=pm, y=y, cl=(ev, rnd)))

print("graded MARKETS (over side only, one row each): %d\n" % len(recs))
if not recs:
    raise SystemExit("nothing graded")


def report(lbl, v):
    if len(v) < 20:
        print("   %-26s n=%d — too few to read" % (lbl, len(v)))
        return
    b = np.array([x["book"] for x in v])
    mo = np.array([x["model"] for x in v])
    y = np.array([x["y"] for x in v])
    d = mo - b
    eps = 1e-9
    llb = float(-(y * np.log(np.clip(b, eps, 1 - eps))
                  + (1 - y) * np.log(np.clip(1 - b, eps, 1 - eps))).mean())
    llm = float(-(y * np.log(np.clip(mo, eps, 1 - eps))
                  + (1 - y) * np.log(np.clip(1 - mo, eps, 1 - eps))).mean())
    c = float(np.corrcoef(d, y)[0, 1]) if d.std() > 1e-9 else float("nan")
    se = 1.0 / np.sqrt(len(v) - 3)
    print("   %-26s n=%3d  book LL %.4f  model LL %.4f  gap %+5.1fpt   "
          "corr(m-b, y) %+.3f (%.1f SE)" % (lbl, len(v), llb, llm, 100 * (llm - llb), c, c / se))


print("=" * 92)
print("BY ROUND — does disagreement predict better once the model has completed rounds?")
print("=" * 92)
for rnd in sorted({x["rnd"] for x in recs}):
    report("round %d" % rnd, [x for x in recs if x["rnd"] == rnd])

print("\n" + "=" * 92)
print("EARLY (R1) vs LATE (R3/R4) — the charter's in-play question, same population")
print("=" * 92)
report("R1 — no event info", [x for x in recs if x["rnd"] == 1])
report("R2 — 1 round known", [x for x in recs if x["rnd"] == 2])
report("R3/R4 — 2-3 known", [x for x in recs if x["rnd"] >= 3])

print("\n" + "=" * 92)
print("BETTING THE DISAGREEMENT (top quartile of model-minus-book), by round group")
print("=" * 92)
for lbl, v in (("R1", [x for x in recs if x["rnd"] == 1]),
               ("R3/R4", [x for x in recs if x["rnd"] >= 3])):
    if len(v) < 20:
        continue
    d = np.array([x["model"] - x["book"] for x in v])
    thr = np.quantile(d, 0.75)
    sel = [x for x, dd in zip(v, d) if dd >= thr]
    pnl = sum((x["od"] - 1.0) if x["y"] > 0 else -1.0 for x in sel)
    print("   %-8s top-quartile disagreement n=%3d  %+7.2fu  ROI %+6.1f%%  (hit %4.1f%%)"
          % (lbl, len(sel), pnl, 100 * pnl / len(sel),
             100 * np.mean([x["y"] for x in sel])))
