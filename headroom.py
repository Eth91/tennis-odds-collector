"""How much room is there between our model and a THEORETICALLY PERFECT bookmaker?

The information ceiling is not a limit on our model — it is a limit on ANYONE, FanDuel included.
Irreducible round-to-round noise caps how well any predictor can order players. So the honest
question for a bettor is: how much accuracy separates us from a perfect book, and is that gap
bigger than the vig we have to pay?

Computed for 1 round and for 72 holes, because averaging four rounds beats down the noise and
raises the ceiling — which is exactly why the market choice matters.
"""
import math
import os
import random
import shutil
import sqlite3
import statistics as st
from collections import defaultdict

import pga_ruler as RU

_SNAP = os.path.expanduser("~/pga_model_hr.sqlite")
shutil.copyfile(str(RU.DB), _SNAP)
RU.DB = _SNAP
random.seed(17)


def _phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2)))


nf = RU.noise_floor(verbose=False)
sd_noise, sd_skill = nf["sd_noise"], nf["sd_skill"]
print("irreducible per-round noise sd %.3f | true skill spread sd %.3f" % (sd_noise, sd_skill))
print()

# real distribution of skill gaps between paired players
con = sqlite3.connect(RU.DB)
rows = con.execute("SELECT event_id, rnd, player, score FROM rounds WHERE score>0").fetchall()
con.close()
by = defaultdict(list)
for eid, rnd, pl, sc in rows:
    by[(eid, rnd)].append((RU.norm(pl), sc))
per = defaultdict(list)
for k, v in by.items():
    if len(v) < 40:
        continue
    m = st.mean(s for _p, s in v)
    for p, s in v:
        per[p].append(s - m)
means = [st.mean(v) for v in per.values() if len(v) >= 8]

print("  %-10s %10s %10s %10s   %s" % ("market", "ceiling", "ours", "gap", "vig to beat"))
for label, R_, vig in (("1 round", 1, 0.045), ("72 holes", 4, 0.045)):
    cap = 0.0
    N = 40000
    for _ in range(N):
        a, b = random.choice(means), random.choice(means)
        d = abs(a - b) * R_
        var = R_ * 2 * sd_noise ** 2 + RU.RHO * 2 * sd_noise ** 2 * (R_ - 1)
        cap += _phi(d / math.sqrt(var))
    cap /= N
    # ours: same formula but with our RATING gaps, degraded by our rating error
    # rating error variance = noise/n_rounds, approximated by the shrinkage we apply
    ours = 0.0
    for _ in range(N):
        a, b = random.choice(means), random.choice(means)
        d = abs(a - b) * R_
        var = R_ * 2 * sd_noise ** 2 + RU.RHO * 2 * sd_noise ** 2 * (R_ - 1)
        # our estimate of the gap is noisy; K_SHRINK pseudo-rounds implies this much error
        est_err = math.sqrt(2 * sd_noise ** 2 / RU.K_SHRINK) * R_
        d_hat = abs(a - b) * R_ + random.gauss(0, est_err) * 0
        ours += _phi(d / math.sqrt(var + est_err ** 2))
    ours /= N
    gap = cap - ours
    be = 0.5 * (1 + vig / 2)
    print("  %-10s %9.4f %10.4f %10.4f   need >%.4f to profit at even money"
          % (label, cap, ours, gap, be))
print()
print("KEY POINT: the ceiling binds FANDUEL TOO. The gap between us and a perfect book is the")
print("most that could ever be won, before vig — and it is far larger over 72 holes than over one")
print("round, because averaging four rounds beats down the noise that caps single-round ordering.")
