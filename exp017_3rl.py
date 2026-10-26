#!/usr/bin/env python3
"""EXP-017 — 3rd Round Leader vs close. The pre-registered market, now unblocked.

St Jude 2026 R3 is complete (66 of 68 players posted) and 68 closes are held for 3rd Round Leader.
Top-N still needs R4 and stays blocked.

WHY THIS ONE MATTERS MOST OF THE FIELD MARKETS. EXP-013/015 measured the vig on every family:
round-leader holds 32.1% at R1, 26.7% at R2 and 16.0% at R3, and under a Shin devig the
favourite-end charge at R3 is +13.0% against +34.2% at R1. It is the cheapest leader market by a
wide margin, so if the model is ever going to show against a field-win price, this is where.

SETTLEMENT RESOLVED FROM THE BOOK'S OWN PRICES, as in EXP-012, before anything is graded: if this
is the 54-HOLE leader the price must track the 36-hole leaderboard hard; if it is the low R3 score
it must look like a talent market. corr(devigged prob, 36-hole total) decides it with no model
involved. Grading the wrong rule produces a confident answer to a question nobody asked.

MODEL. A 54-hole leader market priced before R3 knows R1 and R2, so an unconditional simulation is
the wrong object -- it would throw away the two rounds the market is entirely about. Only R3 is
drawn, on top of the known 36-hole totals.
    frozen      R3 ~ N(mu, sigma^2)                          RHO plays no role in a single round
    form-adj    R3 ~ N(mu + rho*d, sigma^2(1-rho^2))         d = 36-hole residual
Both rho values are reported: the shipped 0.050 and the 0.085 measured in GM-007/008. This is a
GRADING, so the frozen model is the headline and the research value is shown alongside; the
charter forbids tuning on a pre-registered result.

tau is omitted deliberately: a shared per-round shock adds the same strokes to everyone and cannot
change a rank.
"""
import math
import sqlite3
from collections import defaultdict

import numpy as np

import pga_market as PM
import pga_ruler as RU
import pga_sim as PS

EPS = 1e-9
N = 200000
ASOF = "2026-08-15"

m = sqlite3.connect("file:golf_moves.sqlite?mode=ro", uri=True, timeout=60)
rows = m.execute("SELECT event, runner, close_odds, close_ts, tee_utc FROM moves "
                 "WHERE market=? AND event LIKE ? AND close_odds IS NOT NULL",
                 ("3rd Round Leader", "%St Jude%")).fetchall()
m.close()
snap = defaultdict(dict)
tees = set()
for ev, run, od, ts, tee in rows:
    snap[str(ts)][RU.norm(run)] = float(od)
    if tee:
        tees.add(str(tee))
print("tee stamped on rows: %s" % (sorted(tees) or "NONE"))
for t in sorted(snap):
    print("   snapshot %s  runners %d" % (t, len(snap[t])))
quotes = snap[sorted(snap)[-1]]

fair, info = PM.fair("3rd Round Leader", quotes, n_runners=len(quotes))
if not fair:
    raise SystemExit("pricing refused: %s" % info)
print("\nkind=%s  overround %.3f  hold %.1f%%  runners %d"
      % (info["kind"], info["overround"], info["hold_pct"], len(fair)))

r = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
eid = r.execute("SELECT event_id FROM rounds WHERE event LIKE ? AND date LIKE ? LIMIT 1",
                ("%St. Jude%", "2026%")).fetchone()[0]
byp = defaultdict(dict)
for pl, rd, s in r.execute("SELECT player, rnd, score FROM rounds WHERE event_id=?", (eid,)):
    byp[RU.norm(pl)][int(rd)] = float(s)
r.close()
t36 = {p: v[1] + v[2] for p, v in byp.items() if 1 in v and 2 in v}
t54 = {p: v[1] + v[2] + v[3] for p, v in byp.items() if all(k in v for k in (1, 2, 3))}
r3 = {p: v[3] for p, v in byp.items() if 3 in v}
print("36-hole %d | R3 scores %d | 54-hole %d" % (len(t36), len(r3), len(t54)))

# ---- settlement discriminator, model-free ----
common = [p for p in fair if p in t36]
x = np.array([fair[p] for p in common])
y = np.array([t36[p] for p in common])
print("\n" + "=" * 84)
print("SETTLEMENT (model-free): corr(3RL prob, 36-hole total) = %+.3f over %d runners"
      % (float(np.corrcoef(x, y)[0, 1]), len(common)))
print("   strongly NEGATIVE => the price knows the 36-hole board => 54-HOLE leader market")
print("=" * 84)
for lbl, d in (("lowest R3 score", r3), ("lowest 54-hole total", t54)):
    if d:
        lo = min(d.values())
        w = sorted(p for p, s in d.items() if s == lo)
        print("   %-22s low %g by %d: %s" % (lbl, lo, len(w), ", ".join(z[:20] for z in w[:4])))

lo = min(t54.values())
win = {p for p, s in t54.items() if s == lo}
share = 1.0 / len(win)
print("\n   graded as 54-HOLE leader: %s (dead-heat share %.4f)"
      % (", ".join(sorted(win)), share))

# ---- model ----
R, _g = PS.ratings_asof(ASOF)
cand = [p for p in t36 if p in fair and PS.lookup(R, p) is not None]
names, mu, sg, unrated, coll, dup = PS.field_ratings(cand, R, spread=1.30)
if unrated or dup:
    print("   unrated %s | duplicates %s" % (unrated, dup))
t36v = np.array([t36[p] for p in names])
d36 = (t36v - 2 * mu) - float(np.mean(t36v - 2 * mu))       # 36-hole residual, centred
print("\nmodel field %d/%d priced runners" % (len(names), len(fair)))


def leader_p(shift, scale, seed):
    rng = np.random.default_rng(seed)
    acc = np.zeros(len(names))
    step = 20000
    for s0 in range(0, N, step):
        k = min(step, N - s0)
        r3s = np.rint(mu + shift + scale * rng.standard_normal((k, len(names))))
        tt = t36v[None, :] + r3s
        best = tt.min(1, keepdims=True)
        tie = (tt == best)
        acc += (tie / tie.sum(1, keepdims=True)).sum(0)
    return acc / N


y = np.array([share if p in win else 0.0 for p in names])
pb = np.array([fair[p] for p in names])
od = np.array([quotes[p] for p in names])
llb = float(-(y * np.log(np.clip(pb, EPS, 1)) + (1 - y) * np.log(np.clip(1 - pb, EPS, 1))).mean())

print("\n" + "=" * 88)
print("GRADED — 54-hole leader, dead-heat settled, model vs devigged close")
print("=" * 88)
variants = [("frozen (no form update)", np.zeros(len(names)), sg)]
for rho in (0.050, 0.085):
    variants.append(("form-adj rho=%.3f%s" % (rho, "  [GM-007 measured]" if rho > 0.06 else ""),
                     rho * d36 / 2.0, sg * math.sqrt(max(1 - rho * rho, 1e-9))))
wi = [i for i, p in enumerate(names) if p in win][0]
for lbl, shift, scale in variants:
    pm_ = leader_p(shift, scale, 77)
    llm = float(-(y * np.log(np.clip(pm_, EPS, 1))
                  + (1 - y) * np.log(np.clip(1 - pm_, EPS, 1))).mean())
    wm = [i + 1 for i, j in enumerate(np.argsort(-pm_)) if names[j] in win]
    wb = [i + 1 for i, j in enumerate(np.argsort(-pb)) if names[j] in win]
    ev = pm_ * od - 1.0
    fl = np.where(ev >= 0.03)[0]
    pnl = float(sum((od[i] - 1.0) * (1 if y[i] > 0 else 0) - (0 if y[i] > 0 else 1) for i in fl))
    print("\n   %s" % lbl)
    print("      model LL %.5f  book LL %.5f  gap %+.2f pts -> %s"
          % (llm, llb, (llm - llb) * 100, "MODEL BETTER" if llm < llb else "BOOK BETTER"))
    print("      winner rank model %s | book %s (of %d) | p(winner) model %.4f book %.4f"
          % (wm, wb, len(names), pm_[wi], pb[wi]))
    print("      EV>=3%% flags %d -> %+.2fu | max EV in field %+.3f"
          % (len(fl), pnl, float(ev.max())))
print("\n   corr(model, book) = %+.3f"
      % float(np.corrcoef(leader_p(np.zeros(len(names)), sg, 77), pb)[0, 1]))
