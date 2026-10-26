#!/usr/bin/env python3
"""EXP-006 — the simulator as ARBITER: does the book know something the base rate does not?

EXP-005 found the book differentiates players at the 4.5 birdie line far more than their base
rates justify. Across 104 selections the book's under price moves 0.597 -> 0.544 -> 0.476 by
price bucket while the leave-one-out base rate stays flat at ~0.60 (clustered z=+3.63, 79% of
selections have base > book). At 3.5 the sign REVERSES (z=-2.47), so this is not "unders are
always cheap".

Two readings, and only one is bettable:
  BOOK IS RIGHT  it prices course, conditions and current form, which a career base rate ignores.
                 The players it prices at 2.00 really are more birdie-prone THIS week.
  BOOK IS WRONG  it over-differentiates, and the flat base rate is the better estimate.

The simulator is the natural arbiter because it knows exactly the things the base rate does not —
course par mix, course factor, wind, and decayed recent form. So:

    corr(model, book)  vs  corr(model, base)

If the model tracks the BOOK's differentiation, the book is reading real week-specific signal and
the base-rate "edge" is naive. If the model tracks the FLAT base rate, the book is manufacturing
differences and there is something to bet.

⚠️ This is the first experiment where the simulator could earn its place in the birdie stream. It
has so far added nothing — EXP-004's model-ish filter dropped 3 of 104 selections and changed
nothing. A null here means the ARMED record is riding a market feature, not the model.
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


# the model's per-player birdie rates, as the live stream computes them
# rates() returns (player_rates, field_rates) — a tuple, not a dict. Unpack it.
try:
    rates, _field = PB.rates()
    print("model rates for %d players" % len(rates))
except Exception as e:                                                     # noqa: BLE001
    raise SystemExit("cannot load model rates: %s" % str(e)[:90])

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
        others = [b for (t, rr, b) in allr.get(key, []) if not (t == tn and rr == rnd)]
        if len(others) < 25:
            continue
        base = float(np.mean([1.0 if b < line else 0.0 for b in others]))
        pr = rates.get(key) or rates.get(pl)
        if not pr:
            continue
        try:                          # model P(>= line+0.5) -> P(under) = 1 - that
            p_over = PB.p_x_or_more(pr, int(line + 0.5))
        except Exception:                                                  # noqa: BLE001
            continue
        if p_over is None:
            continue
        recs.append(dict(pl=pl, line=line, od=q[run], book=pf, base=base,
                         model=1.0 - float(p_over), y=1.0 if a < line else 0.0, cl=(ev, rnd)))

print("selections with model + book + base: %d\n" % len(recs))
for line in sorted({x["line"] for x in recs}):
    v = [x for x in recs if x["line"] == line]
    if len(v) < 20:
        continue
    b = np.array([x["book"] for x in v])
    ba = np.array([x["base"] for x in v])
    mo = np.array([x["model"] for x in v])
    y = np.array([x["y"] for x in v])
    print("=" * 74)
    print("UNDER %.1f   n=%d" % (line, len(v)))
    print("=" * 74)
    print("   mean:  book %.4f   base %.4f   model %.4f   realised %.4f"
          % (b.mean(), ba.mean(), mo.mean(), y.mean()))
    print("   sd:    book %.4f   base %.4f   model %.4f" % (b.std(), ba.std(), mo.std()))
    print("   ARBITRATION — who does the model resemble?")
    print("      corr(model, book) = %+.3f" % np.corrcoef(mo, b)[0, 1])
    print("      corr(model, base) = %+.3f" % np.corrcoef(mo, ba)[0, 1])
    print("      corr(book,  base) = %+.3f" % np.corrcoef(b, ba)[0, 1])
    # does the model's DISAGREEMENT with the book predict the outcome?
    d = mo - b
    if d.std() > 1e-9:
        print("   does model-minus-book predict the result?  corr = %+.3f (n=%d)"
              % (np.corrcoef(d, y)[0, 1], len(v)))
    print("   by price bucket:")
    bb = defaultdict(list)
    for x in v:
        bb[round(x["od"] * 4) / 4].append(x)
    for od in sorted(bb):
        vv = bb[od]
        if len(vv) >= 5:
            print("      @%.2f n=%3d  book %.3f  base %.3f  MODEL %.3f  realised %.3f"
                  % (od, len(vv), np.mean([z["book"] for z in vv]),
                     np.mean([z["base"] for z in vv]), np.mean([z["model"] for z in vv]),
                     np.mean([z["y"] for z in vv])))
    print()
