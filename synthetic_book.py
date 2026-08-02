"""The one price-based backtest that IS possible without a price archive.

We cannot test "does the model beat FanDuel" historically: golf_lines starts 2026-07-27 and
covers one unplayed event, so G2 is n=0, and substituting another book's history would break the
REAL LINES ONLY rule that cost 6-7 points of inflation on WNBA.

But a NECESSARY condition is testable right now. A bookmaker's price is, at worst, about as good
as the best public model plus vig. So:

    if the model cannot beat a synthetic book built from a decent public baseline,
    it certainly cannot beat the real one.

Passing does NOT prove we beat FanDuel — the real book is better than any baseline here. Failing
would be decisive though, and the SIZE of the margin says how much room there is above the vig.

Three books, weakest to strongest:
  NAIVE      unweighted mean of a player's last 20 field-relative rounds, global sigma. What
             someone with a spreadsheet would build.
  PRE-CALIB  this model as it stood yesterday morning — RHO 0.25, K_SHRINK 12, SIG_SHRINK 20,
             HALF_LIFE 120. Measures whether today's calibration work bought anything real.
  SELF       the current model as its own opponent. Must return ~0 ROI at any vig; a positive
             number here means the harness is broken, so it is the control.

Every book is quoted with a real 4.5% two-way overround, and bets are settled on actual results.
"""
import math
import random
import sqlite3
import statistics as st
from collections import defaultdict

import os
import shutil

import pga_ruler as RU

# snapshot: the loop rewrites the tracked DB under long readers
_SNAP = os.path.expanduser("~/pga_model_sb.sqlite")
shutil.copyfile(str(RU.DB), _SNAP)
RU.DB = _SNAP

random.seed(3)
VIG = 0.045                # two-way overround the synthetic book charges
EDGE = 0.06                # M_EDGE, the live matchup threshold
PAIRS_PER_EVENT = 400

con = sqlite3.connect(RU.DB)
evs = con.execute("SELECT event_id, MIN(date) d FROM rounds GROUP BY event_id "
                  "HAVING d >= '2026-01-01' ORDER BY d").fetchall()
con.close()
rows_all = RU.all_rows()


def naive_ratings(asof):
    """Unweighted mean of each player's last 20 field-relative rounds; global sigma."""
    rows = [r for r in rows_all if r[1] < asof]
    by_er = defaultdict(list)
    for eid, _d, _nm, rnd, sc in rows:
        by_er[(eid, rnd)].append(sc)
    fm = {k: st.mean(v) for k, v in by_er.items() if len(v) >= 20}
    per = defaultdict(list)
    for eid, _d, nm, rnd, sc in rows:
        m = fm.get((eid, rnd))
        if m is not None:
            per[RU.norm(nm)].append(sc - m)
    g = st.pstdev([x for v in per.values() for x in v]) or 2.8
    out = {}
    for nm, v in per.items():
        last = v[-20:]
        if len(last) >= 5:
            out[nm] = (st.mean(last), g, len(v))
    return out


def prob(R, a, b, rho):
    old = RU.RHO
    RU.RHO = rho
    p = RU.matchup_prob(R, a, b, rounds=4)
    RU.RHO = old
    return p


BOOKS = {
    "NAIVE (last-20 mean)": None,
    "PRE-CALIB (yesterday)": dict(k_shrink=12.0, sig_shrink=20.0, half_life=120.0, rho=0.25),
    "SELF (control)": dict(k_shrink=None, sig_shrink=None, half_life=None, rho=RU.RHO),
}
res = {k: {"bets": 0, "won": 0, "pnl": 0.0} for k in BOOKS}
n_ev = 0

for eid, d0 in evs:
    con = sqlite3.connect(RU.DB)
    rr = con.execute("SELECT player, SUM(score), COUNT(*) FROM rounds WHERE event_id=? "
                     "AND score>0 GROUP BY player", (eid,)).fetchall()
    con.close()
    full = {RU.norm(p): t for p, t, n in rr if n == 4 and t}
    if len(full) < 50:
        continue
    Rme, _ = RU.fit(asof=d0, rows=rows_all)
    Rme = {RU.norm(k): v for k, v in Rme.items()}
    Rnaive = naive_ratings(d0)
    Rpre, _ = RU.fit(asof=d0, rows=rows_all, k_shrink=12.0, sig_shrink=20.0, half_life=120.0)
    Rpre = {RU.norm(k): v for k, v in Rpre.items()}
    fl = [p for p in full if p in Rme]
    if len(fl) < 40:
        continue
    n_ev += 1
    for _ in range(PAIRS_PER_EVENT):
        a, b = random.choice(fl), random.choice(fl)
        if a == b or full[a] == full[b]:
            continue
        y = 1.0 if full[a] < full[b] else 0.0
        p_me = prob(Rme, a, b, RU.RHO)
        if p_me is None:
            continue
        for label, cfg in BOOKS.items():
            if cfg is None:
                if a not in Rnaive or b not in Rnaive:
                    continue
                p_bk = prob(Rnaive, a, b, RU.RHO)
            elif label.startswith("SELF"):
                p_bk = p_me
            else:
                p_bk = prob(Rpre, a, b, cfg["rho"])
            if p_bk is None:
                continue
            # the book quotes both sides with the overround split evenly
            for side, pm, pb, res_y in ((0, p_me, p_bk, y), (1, 1 - p_me, 1 - p_bk, 1 - y)):
                implied = pb * (1 + VIG / 2.0)
                if implied <= 0 or implied >= 1:
                    continue
                odds = 1.0 / implied
                if pm - implied >= EDGE:
                    r = res[label]
                    r["bets"] += 1
                    r["won"] += res_y
                    r["pnl"] += (odds - 1) if res_y else -1.0

print("events: %d, vig %.1f%%, edge threshold %.0f pts" % (n_ev, 100 * VIG, 100 * EDGE))
print()
print("  %-24s %7s %7s %8s %9s" % ("synthetic book", "bets", "won", "hit%", "ROI"))
for label in BOOKS:
    r = res[label]
    if not r["bets"]:
        print("  %-24s %7d   (no bets cleared the threshold)" % (label, 0))
        continue
    roi = r["pnl"] / r["bets"]
    print("  %-24s %7d %7.0f %7.1f%% %+8.1f%%"
          % (label, r["bets"], r["won"], 100 * r["won"] / r["bets"], 100 * roi))
print()
print("  SELF must sit near 0% — it is the control. A positive SELF means the harness is broken.")
print("  NAIVE and PRE-CALIB show the margin over weaker opponents; the real book is better than")
print("  both, so these are UPPER BOUNDS on the available edge, not forecasts of profit.")
