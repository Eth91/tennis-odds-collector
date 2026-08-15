#!/usr/bin/env python3
"""EXP-015 — does EXP-013's "UNREACHABLE" verdict survive a different devig? Testing my own claim.

EXP-013 struck every field-wide market off the research programme on the basis of its hold: round
leader 26.7%, win 28.0%, top-5 incl. ties 35.9%. That verdict inherits an ASSUMPTION I made and
flagged: pga_market devigs PROPORTIONALLY, which makes the per-runner vig constant by construction.
Every runner in a 26.7% book is then a 26.7% loser, and no model reaches that.

Real books do not price that way. The favourite-longshot bias is one of the most replicated
findings in betting markets: longshots carry far more vig than favourites. If that holds here, the
FAVOURITE end of a 69-man field could be far cheaper than the book average, and "unreachable"
would be an artifact of my devig rather than a property of the market.

WHAT THIS CAN AND CANNOT DO. It cannot prove which devig is correct — that needs realised
frequencies across the price range, and the only field-market outcomes in hand are two single
winners (1RL and 2RL). This is therefore a SENSITIVITY analysis, stated as one: how far does the
favourite-end EV move between devig models, and does any of them lift a real selection to
break-even? If the verdict is stable across all three, it stands. If Shin flips it, EXP-013's
strike-off is premature and field markets go back on the list pending more events.

  proportional  p_i = q_i / sum(q)                        (current; constant vig)
  power         p_i = q_i^k, k solved so sum = 1          (compresses longshots)
  Shin          p_i from Shin's insider-trading model     (the standard FL correction)

Shin: given raw implied q_i summing to R, solve z in [0, 1) with
    p_i = (sqrt(z^2 + 4(1-z) q_i^2 / R) - z) / (2(1-z))
and z chosen so sum(p) = 1. z is the implied insider fraction; z=0 collapses to proportional.
"""
import math
import sqlite3
from collections import defaultdict

import numpy as np

import pga_market as PM
import pga_ruler as RU

EPS = 1e-12


def power_devig(q):
    lo, hi = 0.2, 3.0
    for _ in range(80):
        k = 0.5 * (lo + hi)
        if sum(x ** k for x in q) > 1.0:
            lo = k
        else:
            hi = k
    k = 0.5 * (lo + hi)
    return [x ** k for x in q], k


def shin_devig(q):
    R = sum(q)
    lo, hi = 0.0, 0.99
    for _ in range(200):
        z = 0.5 * (lo + hi)
        s = sum((math.sqrt(z * z + 4 * (1 - z) * x * x / R) - z) / (2 * (1 - z)) for x in q)
        if s > 1.0:
            lo = z
        else:
            hi = z
    z = 0.5 * (lo + hi)
    return [(math.sqrt(z * z + 4 * (1 - z) * x * x / R) - z) / (2 * (1 - z)) for x in q], z


m = sqlite3.connect("file:golf_moves.sqlite?mode=ro", uri=True, timeout=60)
rows = m.execute("SELECT event, market, mtype, runner, close_odds, close_ts FROM moves "
                 "WHERE close_odds IS NOT NULL AND mtype IN "
                 "('WIN_ONLY_IMG','ROUND_LEADER_IMG','TOP_5_FINISH_IMG','TOP_10_FINISH_IMG',"
                 "'TOP_20_FINISH_IMG','TOP_5_FINISH_(INCL._TIES)','TOP_10_FINISH_(INCL._TIES)',"
                 "'TOP_20_FINISH_(INCL._TIES)','OUTRIGHT_WINNER_WITHOUT_X_IMG')").fetchall()
m.close()
best = {}
for ev, mk, mt, run, od, ts in rows:
    k = (" ".join(str(ev).split()), mk, RU.norm(run))
    if k not in best or str(ts) > best[k][0]:
        best[k] = (str(ts), float(od), mt)
books, meta = defaultdict(dict), {}
for (ev, mk, run), (_ts, od, mt) in best.items():
    books[(ev, mk)][run] = od
    meta[(ev, mk)] = mt
print("field-wide books: %d\n" % len(books))

print("=" * 96)
print("PER-RUNNER VIG BY PRICE RANK, under three devigs")
print("=" * 96)
print("%-26s %5s %7s %6s  %-28s %-28s"
      % ("market", "n", "hold", "z", "vig on the 5 SHORTEST prices", "vig on the 5 LONGEST"))
summary = []
for k, q in sorted(books.items(), key=lambda x: meta[x[0]]):
    mt = meta[k]
    f, info = PM.fair(k[1], q, n_runners=len(q))
    if not f or info.get("kind") not in (PM.FIELD_WIN, PM.TOP_N):
        continue
    tgt = float(info["target_sum"])
    runs = sorted(q, key=lambda r: q[r])                 # shortest price first
    raw = [1.0 / q[r] for r in runs]
    # normalise to the market's own target so top-N (target N) is handled on the same footing
    rr = [x / tgt for x in raw]
    prop = [x / sum(rr) for x in rr]
    pw, kk = power_devig(rr)
    sh, z = shin_devig(rr)
    # Per-runner vig = what you are charged over fair, at the offered price: implied_i / fair_i - 1.
    # BOTH sides must be on the same scale. rr is implied rescaled so a fair book sums to 1, and
    # every devig below returns p on that same scale, so the comparison is rr_i / p_i. Rebuilding
    # implied from the odds here instead re-applied the target and made top-N read a 40000% vig
    # (off by N^2); field-win markets hid it because their target is 1.
    def vig(p):
        return [ri / max(pi, EPS) - 1.0 for ri, pi in zip(rr, p)]
    v_prop, v_pw, v_sh = vig(prop), vig(pw), vig(sh)
    n5 = min(5, len(runs))
    summary.append((mt, k[1], len(runs), info["hold_pct"], z, kk,
                    float(np.mean(v_sh[:n5])), float(np.mean(v_sh[-n5:])),
                    float(np.mean(v_pw[:n5])), float(np.mean(v_pw[-n5:])),
                    float(np.mean(v_prop[:n5]))))
    print("%-26s %5d %6.1f%% %6.3f  shin %+6.1f%% power %+6.1f%%   shin %+6.1f%% power %+6.1f%%"
          % (str(k[1])[:26], len(runs), info["hold_pct"], z,
             100 * np.mean(v_sh[:n5]), 100 * np.mean(v_pw[:n5]),
             100 * np.mean(v_sh[-n5:]), 100 * np.mean(v_pw[-n5:])))

print("\n" + "=" * 96)
print("DOES THE VERDICT MOVE? proportional charges every runner the book average.")
print("=" * 96)
if summary:
    pr = np.array([s[10] for s in summary])
    sf = np.array([s[6] for s in summary]); sl = np.array([s[7] for s in summary])
    pf = np.array([s[8] for s in summary]); pl = np.array([s[9] for s in summary])
    print("   favourites (5 shortest): proportional %+6.1f%%   shin %+6.1f%%   power %+6.1f%%"
          % (100 * pr.mean(), 100 * sf.mean(), 100 * pf.mean()))
    print("   longshots  (5 longest ): proportional %+6.1f%%   shin %+6.1f%%   power %+6.1f%%"
          % (100 * pr.mean(), 100 * sl.mean(), 100 * pl.mean()))
    print("\n   Shin moves the favourite-end charge by %+.1f points vs proportional."
          % (100 * (sf.mean() - pr.mean())))
    best_fav = 100 * min(sf.min(), pf.min())
    print("   cheapest favourite-end vig seen under ANY devig: %+.1f%%" % best_fav)
    print("\n   VERDICT: %s" % (
        "STANDS — even the favourite end under the most generous devig is dearer than any\n"
        "            edge demonstrated anywhere in this programme (best disagreement corr so far\n"
        "            is NEGATIVE)." if best_fav > 6 else
        "OVERTURNED — the favourite end is reachable; field markets go back on the list."))
