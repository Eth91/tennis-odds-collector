#!/usr/bin/env python3
"""TN-027 — do form/surface/fatigue/H2H add over PINNACLE? Oriented by NAME-SORT, not by outcome.

TWO EARLIER DESIGNS FAILED, and both failures were mine:

  winner-oriented only  every row had y=1, so the logistic fit drove the intercept to infinity and
                        every feature "helped" by the entire log-loss.
  mirrored rows         emitting (z, y=1) and (-z, y=0) ties the feature's SIGN to the LABEL by
                        construction. Any feature with a winner/loser asymmetry then separates the
                        classes perfectly - which is why rest_days came back at t=-73 and a 0.14
                        log-loss "improvement" over a sharp closing price.

The asymmetry is real and mundane: winners average rest_days -8.4 and load_14 +1.2, in EVERY round
including the first, because better players are active players - lose early last week and you get
more rest and fewer recent matches. That is a quality proxy, not fatigue, and Pinnacle prices
quality already.

CORRECT DESIGN: orient every match by NAME-SORT, independent of who won. p1 is simply the
alphabetically first player; y = 1 if p1 won; features are p1-minus-p2; the price is P(p1 wins).
Now the label genuinely varies, nothing is constructed from the outcome, and a feature only earns a
coefficient by actually predicting.
"""
import math
import re
import sqlite3
import statistics as st
import unicodedata
from collections import defaultdict, deque
from datetime import date as DT
from pathlib import Path

import numpy as np

DB = Path(__file__).resolve().parent / "tennis_ace.sqlite"
EPS = 1e-9


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", s.lower()).strip()


def ktml(n):
    p = [x for x in norm(n).split() if x]
    return "%s|%s" % (" ".join(p[1:]), p[0][:1]) if len(p) >= 2 else None


con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=60)
M = con.execute("""SELECT date, year, surface, player, opp, player_rank, opp_rank, player_ht,
                          opp_ht FROM ace_pm
                   WHERE won=1 AND surface IS NOT NULL AND surface!='' ORDER BY date""").fetchall()
oh = defaultdict(list)
for d, wk, lk, wo, lo in con.execute("SELECT date, wkey, lkey, w_odds, l_odds FROM odds_hist"):
    oh[(wk, lk)].append((d, wo, lo))
con.close()


def shin2(o1, o2):
    q = [1.0 / o1, 1.0 / o2]
    R = sum(q)
    lo, hi = 0.0, 0.99
    for _ in range(120):
        z = 0.5 * (lo + hi)
        s = sum((math.sqrt(z * z + 4 * (1 - z) * x * x / R) - z) / (2 * (1 - z)) for x in q)
        if s > 1.0:
            lo = z
        else:
            hi = z
    z = 0.5 * (lo + hi)
    p = [(math.sqrt(z * z + 4 * (1 - z) * x * x / R) - z) / (2 * (1 - z)) for x in q]
    return p[0] / sum(p)


def price(d, w, l):
    kw, kl = ktml(w), ktml(l)
    if not kw or not kl:
        return None
    for dd, wo, lo in oh.get((kw, kl), []):
        try:
            if abs((DT.fromisoformat(dd) - DT.fromisoformat(d)).days) <= 4:
                return shin2(wo, lo)
        except Exception:                                               # noqa: BLE001
            continue
    return None


K = 24.0
elo = defaultdict(lambda: 1500.0)
elo_s = defaultdict(lambda: defaultdict(lambda: 1500.0))
last10 = defaultdict(lambda: deque(maxlen=10))
lastdate, recent = {}, defaultdict(list)
h2h = defaultdict(lambda: [0, 0])
rows = []
for d, yr, surf, w, l, wr, lr, wht, lht in M:
    pw = price(d, w, l)
    if pw is not None and 0.01 < pw < 0.99:
        # ORIENT BY NAME SORT - nothing here may depend on who won
        a, b = (w, l) if norm(w) < norm(l) else (l, w)
        y = 1.0 if a == w else 0.0
        p1 = pw if a == w else 1 - pw
        ra, rb = (wr, lr) if a == w else (lr, wr)
        ha, hb = (wht, lht) if a == w else (lht, wht)

        def form(pl):
            return (sum(last10[pl]) / len(last10[pl])) if len(last10[pl]) >= 5 else None

        def rest(pl):
            return min((DT.fromisoformat(d) - DT.fromisoformat(lastdate[pl])).days, 30) \
                if pl in lastdate else None

        def load(pl):
            return sum(1 for x in recent[pl]
                       if (DT.fromisoformat(d) - DT.fromisoformat(x)).days <= 14)
        f = {}
        fa, fb = form(a), form(b)
        if fa is not None and fb is not None:
            f["form_10"] = fa - fb
            f["form_delta"] = (fa - fb) - ((elo[a] - elo[b]) / 400.0)
        f["surf_edge"] = (elo_s[surf][a] - elo[a]) - (elo_s[surf][b] - elo[b])
        r1, r2 = rest(a), rest(b)
        if r1 is not None and r2 is not None:
            f["rest_days"] = r1 - r2
        f["load_14"] = load(a) - load(b)
        if h2h[(a, b)][0] + h2h[(a, b)][1] >= 2:
            t = h2h[(a, b)][0] + h2h[(a, b)][1]
            f["h2h"] = h2h[(a, b)][0] / t - 0.5
        if ra and rb and ra > 0 and rb > 0:
            f["rank_gap"] = math.log(rb / ra)
        if ha and hb:
            f["ht_gap"] = (ha - hb) / 10.0
        rows.append((yr, p1, y, f))
    pe = 1.0 / (1.0 + 10 ** ((elo[l] - elo[w]) / 400.0))
    elo[w] += K * (1 - pe)
    elo[l] -= K * (1 - pe)
    ps = 1.0 / (1.0 + 10 ** ((elo_s[surf][l] - elo_s[surf][w]) / 400.0))
    elo_s[surf][w] += K * (1 - ps)
    elo_s[surf][l] -= K * (1 - ps)
    last10[w].append(1)
    last10[l].append(0)
    lastdate[w] = d
    lastdate[l] = d
    recent[w].append(d)
    recent[l].append(d)
    h2h[(w, l)][0] += 1
    h2h[(l, w)][1] += 1

tr = [r for r in rows if r[0] <= 2023]
te = [r for r in rows if r[0] >= 2024]
print("priced matches %d | train %d | test %d" % (len(rows), len(tr), len(te)))
print("sanity: p1 win rate should be ~0.50 under name-sort orientation -> %.3f"
      % (sum(r[2] for r in rows) / len(rows)))
print("        mean feature values should be ~0, not winner-skewed:")
for fn in ("rest_days", "load_14", "form_10"):
    v = [r[3][fn] for r in rows if fn in r[3]]
    if v:
        print("           %-10s mean %+.3f" % (fn, st.mean(v)))

print("\n" + "=" * 92)
print("DOES THE FACTOR ADD ANYTHING ON TOP OF PINNACLE?  fit 2015-2023, scored 2024-25")
print("=" * 92)
print("   %-12s %7s %10s %9s %8s %14s" % ("factor", "n", "coef", "SE", "t", "OOS delta LL"))
for fn in ("form_10", "form_delta", "surf_edge", "rest_days", "load_14", "h2h", "rank_gap",
           "ht_gap"):
    D = [(math.log(p / (1 - p)), fr[fn], y) for _yr, p, y, fr in tr if fn in fr]
    T = [(math.log(p / (1 - p)), fr[fn], y) for _yr, p, y, fr in te if fn in fr]
    if len(D) < 500 or len(T) < 200:
        print("   %-12s too few" % fn)
        continue
    X = np.array([[1.0, x, z] for x, z, _ in D])
    Y = np.array([yy for _, _, yy in D])
    b = np.zeros(3)
    b[1] = 1.0
    for _ in range(40):
        q = 1 / (1 + np.exp(-np.clip(X @ b, -30, 30)))
        g = X.T @ (q - Y)
        W = q * (1 - q) + 1e-9
        H = (X * W[:, None]).T @ X
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            break
        b = b - step
        if np.max(np.abs(step)) < 1e-9:
            break
    se = math.sqrt(max(np.linalg.pinv(H)[2][2], 0))
    XT = np.array([[1.0, x, z] for x, z, _ in T])
    YT = np.array([yy for _, _, yy in T])
    base_p = 1 / (1 + np.exp(-XT[:, 1]))
    with_p = 1 / (1 + np.exp(-np.clip(XT @ b, -30, 30)))

    def nll(p):
        p = np.clip(p, EPS, 1 - EPS)
        return float(-(YT * np.log(p) + (1 - YT) * np.log(1 - p)).mean())
    d_ll = nll(with_p) - nll(base_p)
    print("   %-12s %7d %10.4f %9.4f %8.2f %+14.5f%s"
          % (fn, len(T), b[2], se, b[2] / se if se else 0, d_ll,
             "  <- HELPS" if d_ll < -1e-5 else ""))
print()
print("   NEGATIVE OOS delta = the feature improves on Pinnacle. Positive = it does not.")
