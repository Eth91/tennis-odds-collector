#!/usr/bin/env python3
"""EXP-012 — 2nd Round Leader (36-hole) vs the close. Lane B, second field-wide observation.

SETTLEMENT RESOLVED FIRST (exp012_disc.py, no model involved): this is the 36-HOLE LEADER, not
the low round-2 score. corr(devigged 2RL prob, R1 score) = -0.716, and the five largest price
gains from 1RL to 2RL are exactly the five players who shot 65 in R1. A round-2-only market
cannot look like that. Both readings happen to have the same winner here, so the OUTCOME is
robust to the ambiguity -- but the model probability is not, which is why it had to be settled.

TWO SNAPSHOT TIMES, AND ONLY ONE IS THE CLOSE. golf_moves holds the event under two names --
'  PGA FedEx St Jude Championship 2026' (padded) and the clean one -- each with 69 closes, at
09:30:06 and 12:05:02 respectively. That is golf_collect's name-padding fix landing mid-event:
rows moved to the clean name at 09:30. A dict built by iterating rows takes whichever arrives
first and silently MIXES two snapshots 2.5 hours apart. The close is the LAST price before the
deadline, so 12:05 wins per runner, and the 09:30 vector is kept as the contamination control.

CONTAMINATION CONTROL. R2's resolved first tee is 12:10 (pga_tee_gate, 'round-2 leader -> R2
first tee'), so 12:05 is 5 minutes pre-tee. That is asserted, not assumed: if any golf had been
played between 09:30 and 12:05 the two price vectors would diverge violently for the players who
teed off. They are compared below, and the grade is REFUSED if they have.

MODEL. The 36-hole leader is priced knowing R1, so an unconditional simulation is the wrong
object -- it would throw away the head start the whole market is about. P(low 36-hole total) is
computed directly: R1 is known, only R2 is drawn.
    unconditional : R2 ~ N(mu, sig^2)                 -- ignores what R1 said about form
    form-updated  : R2 ~ N(mu + rho*d, sig^2(1-rho^2))-- d = R1 residual, rho = 0.09 (measured)
The week effect is shared across a player's rounds, so an R1 residual is partial evidence about
it; the posterior mean of the week effect given d is rho*d with variance rho(1-rho)sig^2, hence
the form-updated line. Reporting both makes the form update its own miniature test.
tau (the shared per-round conditions shock) is DELIBERATELY OMITTED: it adds the same number of
strokes to every player in the round and therefore cannot change a rank. Including it would only
add variance to the estimate.

⚠️ WHAT THIS CAN AND CANNOT SHOW. n=68 runners, ONE market, ONE event, and exactly ONE winner.
The log-loss difference is dominated by a single player's probability. This is a SECOND
OBSERVATION to sit beside EXP-001, not evidence of an edge, and it is reported as such.
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
SEED = 612
SPREAD = 1.30
ASOF = "2026-08-14"          # rounds strictly before 08-14 -> R2 is not in the training set

# ---------------------------------------------------------------- prices
m = sqlite3.connect("file:golf_moves.sqlite?mode=ro", uri=True, timeout=60)
rows = m.execute("SELECT event, runner, close_odds, close_ts, tee_utc FROM moves "
                 "WHERE market=? AND event LIKE ? AND close_odds IS NOT NULL",
                 ("2nd Round Leader", "%St Jude%")).fetchall()
m.close()
snap = defaultdict(dict)                       # close_ts -> {runner: odds}
tees = set()
for ev, run, od, ts, tee in rows:
    snap[str(ts)][RU.norm(run)] = float(od)
    if tee:
        tees.add(str(tee))
print("tee stamped on the rows: %s" % (sorted(tees) or "NONE"))
for t in sorted(snap):
    print("   snapshot %s  runners %d" % (t, len(snap[t])))

times = sorted(snap)
early, late = snap[times[0]], snap[times[-1]]
both = [p for p in late if p in early]
a = np.array([early[p] for p in both]); b = np.array([late[p] for p in both])
rel = np.abs(b - a) / np.maximum(a, EPS)
print("\nCONTAMINATION CONTROL — %s vs %s over %d shared runners" % (times[0], times[-1], len(both)))
print("   identical prices %d/%d | max relative move %.4f | median %.4f"
      % (int((rel < 1e-9).sum()), len(both), rel.max(), float(np.median(rel))))
if rel.max() > 0.60:
    mv = sorted(zip(both, a, b), key=lambda x: -abs(x[2] - x[1]) / max(x[1], EPS))[:5]
    for p, x, y in mv:
        print("      %-24s %.2f -> %.2f" % (p[:24], x, y))
    raise SystemExit("REFUSED: prices moved like golf was being played between the snapshots")
print("   -> no round-2 information in the later snapshot; it is a clean pre-tee close")

quotes = dict(late)                            # LAST price before the 12:10 deadline
fair, info = PM.fair("2nd Round Leader", quotes, n_runners=len(quotes))
if not fair:
    raise SystemExit("pricing refused: %s" % info)
print("\nkind=%s  overround %.3f  hold %.1f%%  runners %d"
      % (info["kind"], info["overround"], info["hold_pct"], len(fair)))

# ---------------------------------------------------------------- results
r = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
eid = r.execute("SELECT event_id FROM rounds WHERE event LIKE ? AND date LIKE ? LIMIT 1",
                ("%St. Jude%", "2026%")).fetchone()[0]
byp = defaultdict(dict)
for pl, rd, s in r.execute("SELECT player, rnd, score FROM rounds WHERE event_id=?", (eid,)):
    byp[RU.norm(pl)][int(rd)] = float(s)
r.close()
t36 = {p: v[1] + v[2] for p, v in byp.items() if 1 in v and 2 in v}
lo = min(t36.values())
win = {p for p, s in t36.items() if s == lo}
share = 1.0 / len(win)
print("36-hole: %d players, low %g by %d (%s) -> dead-heat share %.4f"
      % (len(t36), lo, len(win), ", ".join(sorted(win)), share))

# ---------------------------------------------------------------- model
R, _g = PS.ratings_asof(ASOF)
r1 = {p: v[1] for p, v in byp.items() if 1 in v}
cand = [p for p in r1 if p in fair and PS.lookup(R, p) is not None]
names, mu, sg, unrated, coll, dup = PS.field_ratings(cand, R, spread=SPREAD)
if unrated or coll or dup:
    print("   unrated %s | collisions %s | duplicates %s" % (unrated, coll, dup))
r1v = np.array([r1[p] for p in names])
rho = float(PS.RHO)
print("\nmodel field %d/%d priced runners | rho %.3f | spread %.2f | n=%d"
      % (len(names), len(fair), rho, SPREAD, N))

# R1 residual, in the model's own units: how far under/over expectation the player played.
d = r1v - (mu + float(np.mean(r1v - mu)))      # centre it: tau/course level is common-mode


def leader_p(shift, scale, seed):
    """P(lowest 36-hole total), dead-heat shared, drawing only R2."""
    rng = np.random.default_rng(seed)
    tot = np.empty((N, len(names)))
    step = 20000
    acc = np.zeros(len(names))
    for s0 in range(0, N, step):
        k = min(step, N - s0)
        r2 = np.rint(mu + shift + scale * rng.standard_normal((k, len(names))))
        tt = r1v[None, :] + r2
        best = tt.min(1, keepdims=True)
        tie = (tt == best)
        acc += (tie / tie.sum(1, keepdims=True)).sum(0)
    return acc / N


variants = [
    ("unconditional (ignores R1 form)", np.zeros(len(names)), sg),
    ("form-updated (rho=%.2f)" % rho, rho * d, sg * math.sqrt(max(1.0 - rho * rho, 1e-9))),
]

print("\n" + "=" * 88)
print("GRADED — 36-hole leader, dead-heat settled, model vs devigged close")
print("=" * 88)
y = np.array([share if p in win else 0.0 for p in names])
pb = np.array([fair[p] for p in names])
od = np.array([quotes[p] for p in names])
llb = float(-(y * np.log(np.clip(pb, EPS, 1)) + (1 - y) * np.log(np.clip(1 - pb, EPS, 1))).mean())

for lbl, shift, scale in variants:
    pm = leader_p(shift, scale, SEED)
    llm = float(-(y * np.log(np.clip(pm, EPS, 1))
                  + (1 - y) * np.log(np.clip(1 - pm, EPS, 1))).mean())
    om = np.argsort(-pm); ob = np.argsort(-pb)
    wm = [i + 1 for i, j in enumerate(om) if names[j] in win]
    wb = [i + 1 for i, j in enumerate(ob) if names[j] in win]
    ev = pm * od - 1.0
    fl = np.where(ev >= 0.03)[0]
    pnl = float(sum((od[i] - 1.0) * (y[i] / share if y[i] > 0 else 0) - (0 if y[i] > 0 else 1)
                    for i in fl))
    print("\n   %s" % lbl)
    print("      model LL %.5f   book LL %.5f   gap %+.2f pts -> %s"
          % (llm, llb, (llm - llb) * 100, "MODEL BETTER" if llm < llb else "BOOK BETTER"))
    print("      winner rank — model %s | book %s (of %d)" % (wm, wb, len(names)))
    print("      model p(winner) %.4f vs book %.4f"
          % (float(pm[[i for i, p in enumerate(names) if p in win][0]]),
             float(pb[[i for i, p in enumerate(names) if p in win][0]])))
    print("      EV>=3%% flags %d -> %+.2fu (ROI %+.1f%%)"
          % (len(fl), pnl, 100 * pnl / len(fl) if len(fl) else 0.0))
    if len(fl):
        top = fl[np.argsort(-ev[fl])][:5]
        print("         " + " | ".join("%s %.0f%% @%.1f" % (names[i][:14], 100 * pm[i], od[i])
                                       for i in top))

print("\n   book alone: p(winner) %.4f, rank %s of %d — the model must beat THIS, not 1/68"
      % (float(pb[[i for i, p in enumerate(names) if p in win][0]]),
         [i + 1 for i, j in enumerate(np.argsort(-pb)) if names[j] in win], len(names)))

# HOW FAR FROM BETTABLE? Zero flags is not a near miss to be re-thresholded -- it is a statement
# about the size of the hold. The EV ceiling and the edge the model would NEED are structural
# facts about these prices and this model, not a coin flip like the single-winner log-loss.
print("\n" + "=" * 88)
print("DISTANCE FROM BETTABLE — why 0 flags, and how far off")
print("=" * 88)
pm = leader_p(np.zeros(len(names)), sg, SEED)          # unconditional = the better of the two
ev = pm * od - 1.0
print("   raw-price EV: max %+.3f  median %+.3f  min %+.3f  (>=+0.03 needed to flag)"
      % (ev.max(), float(np.median(ev)), ev.min()))
print("   best runner: %s  model %.4f  book %.4f  odds %.1f  EV %+.3f"
      % (names[int(np.argmax(ev))][:24], pm[int(np.argmax(ev))],
         pb[int(np.argmax(ev))], od[int(np.argmax(ev))], ev.max()))
need = (1.03 / od.max())
print("   overround %.3f over %d runners => the price already keeps %.1f%% before any skill;"
      % (info["overround"], len(fair), info["hold_pct"]))
print("   to clear +3%% anywhere the model would need to beat the RAW implied by %.0f%% relative."
      % (100 * ((1.03 / (pm * od)).min() - 1.0)))
agree = float(np.corrcoef(pm, pb)[0, 1])
print("   corr(model, book) = %+.3f  |  mean |model-book| = %.4f"
      % (agree, float(np.abs(pm - pb).mean())))
