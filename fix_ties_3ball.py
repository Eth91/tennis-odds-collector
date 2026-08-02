"""Give the simulator INTEGER scores and real ties, then price 3-balls off it.

Golf scores are integers, but simulate() draws continuous normals, so exact ties have probability
zero. Two markets were unpriceable as a direct result:

  TOP-N INCL. TIES  the product pays on 22-26 players, not 20, and the sim's top20 is strictly
                    rank<20 — a ties-EXCLUSIVE quantity. Comparing that to a ties-inclusive price
                    is a category error in the direction that manufactures edge, so it was skipped.
  3-BALLS           P(lowest of three in one round) is materially affected by ties: a two-way tie
                    for low is a dead heat, not a win, and at 18 holes ties are common.

Rounding each simulated round to an integer produces ties at their natural rate, which then gives
both the strict and the ties-inclusive rank distributions from one pass. Positions are computed as
1 + (number strictly better), so a tie shares the better rank — exactly how the books settle
"incl. ties".

Adds: top5_ties/top10_ties/top20_ties alongside the strict versions, and threeball() for the
round-level three-way market.
"""
import ast
import io

p = "pga_ruler.py"
s = io.open(p, encoding="utf-8").read()

old = '''    cutline = np.sort(tot2, axis=1)[:, min(69, k - 1)][:, None]
    made = tot2 <= cutline
    if forced is not None and forced.any():
        made = made | forced[None, :]
    if gone is not None and gone.any():
        made = made & ~gone[None, :]
    tot4 = tot2 + np.where(made, rest, 1e6)
    order = tot4.argsort(1).argsort(1)                    # finishing rank per sim
    out = {}
    for i, p in enumerate(names):
        out[p] = {"win": float((order[:, i] == 0).mean()),
                  "top5": float((order[:, i] < 5).mean()),
                  "top10": float((order[:, i] < 10).mean()),
                  "top20": float((order[:, i] < 20).mean()),
                  "cut": float(made[:, i].mean())}
    return out'''
new = '''    # INTEGER SCORES (2026-07-30). Golf is scored in whole strokes; continuous draws make exact
    # ties impossible, which left top-N-INCL-TIES unpriceable and 3-balls wrong (a two-way tie for
    # low is a dead heat, not a win). Rounding here produces ties at their natural rate and yields
    # BOTH rank distributions from one pass.
    tot2 = np.rint(tot2)
    rest = np.rint(rest)
    cutline = np.sort(tot2, axis=1)[:, min(69, k - 1)][:, None]
    made = tot2 <= cutline
    if forced is not None and forced.any():
        made = made | forced[None, :]
    if gone is not None and gone.any():
        made = made & ~gone[None, :]
    tot4 = tot2 + np.where(made, rest, 1e6)
    order = tot4.argsort(1).argsort(1)                    # strict rank (ties broken arbitrarily)
    # TIE-AWARE POSITION: 1 + how many players are STRICTLY better. A tie shares the better rank,
    # which is how books settle "incl. ties".
    pos = (tot4[:, :, None] > tot4[:, None, :]).sum(2) + 1
    out = {}
    for i, p in enumerate(names):
        out[p] = {"win": float((order[:, i] == 0).mean()),
                  "top5": float((order[:, i] < 5).mean()),
                  "top10": float((order[:, i] < 10).mean()),
                  "top20": float((order[:, i] < 20).mean()),
                  # ties-inclusive: what the "(Incl. Ties)" products actually pay on
                  "win_ties": float((pos[:, i] == 1).mean()),
                  "top5_ties": float((pos[:, i] <= 5).mean()),
                  "top10_ties": float((pos[:, i] <= 10).mean()),
                  "top20_ties": float((pos[:, i] <= 20).mean()),
                  "cut": float(made[:, i].mean())}
    return out


def threeball(R, trio, rounds=1, n_sims=40000, seed=17, course_fit=None):
    """{player: {'win','tie','dead_heat_ev'}} for a 3-ball over `rounds` rounds.

    Integer scores matter here more than anywhere: at 18 holes a two-way tie for low is common,
    and FanDuel settles 3-balls as a dead heat (stake back proportionally) rather than a win. So
    'win' is the outright-low probability and 'dead_heat_ev' is what a unit actually returns —
    a full win plus a half share of two-way ties and a third of three-way ties.
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    keys = []
    for p in trio:
        v = R.get(norm(p)) or R.get(p)
        if not v:
            return {}
        keys.append(v)
    cf = course_fit or {}
    mus = np.array([v[0] + cf.get(p, cf.get(norm(p), 0.0)) for p, v in zip(trio, keys)])
    sig = np.array([v[1] for v in keys])
    wk = rng.normal(0, sig * math.sqrt(RHO), (n_sims, 3))
    eps = rng.normal(0, 1, (n_sims, 3, rounds)) * (sig * math.sqrt(1 - RHO))[None, :, None]
    tot = np.rint((mus + wk)[:, :, None] + eps).sum(2)
    best = tot.min(1, keepdims=True)
    at_best = (tot == best)
    n_at = at_best.sum(1, keepdims=True)
    out = {}
    for i, p in enumerate(trio):
        sole = float(((n_at[:, 0] == 1) & at_best[:, i]).mean())
        tied = float(((n_at[:, 0] > 1) & at_best[:, i]).mean())
        # dead-heat return on a 1u stake: full on a sole win, 1/n of the stake back otherwise
        ev = float((at_best[:, i] / n_at[:, 0]).mean())
        out[p] = {"win": sole, "tie": tied, "dead_heat_ev": ev}
    return out'''
assert old in s, "simulate tail anchor missing"
if "INTEGER SCORES (2026-07-30)" in s:
    print("  = already integer/tie aware")
else:
    s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + simulate(): integer scores, tie-aware positions, *_ties outputs")
    print("  + threeball(): 3-ball pricing with dead-heat EV")
