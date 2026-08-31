#!/usr/bin/env python3
"""TN-025 — do FORM, SURFACE, FATIGUE, H2H or RANK add anything ON TOP OF PINNACLE'S PRICE?

The honest benchmark is the price, not our own model. Earlier work found fatigue/form/streak/H2H
worth about +0.005 AUC over ELO - but beating Elo is easy and irrelevant. If Pinnacle already
prices a factor, knowing it is worth nothing, however real the factor is.

TEST. For every priced match, orient the row to the WINNER (y=1) and fit

    logit P(win) = a + b * logit(p_pinnacle) + c * feature

If c is indistinguishable from zero, the price already contains that factor. Features are signed
as (winner minus loser) so a POSITIVE c means "more of this predicts winning, beyond the price".
Fitted on 2015-2023 and scored on 2024-25; a coefficient that only exists in-sample is noise.

CANDIDATE FACTORS, each one a thing people actually claim moves tennis:
    form_10       win rate over the last 10 matches, difference between the two players
    form_delta    recent form MINUS long-run Elo - "is he playing above himself right now"
    surf_edge     surface Elo minus overall Elo - the "clay-courter on clay" claim
    rest_days     days since last match, capped - freshness
    load_14       matches played in the last 14 days - fatigue
    h2h           head-to-head record between these two, prior meetings only
    rank_gap      log rank ratio - the crudest possible prior
    age_gap, ht_gap  age and height difference

Every feature is built STRICTLY from matches before the one being predicted, accumulated in date
order, so nothing leaks. Pinnacle is SHIN-devigged throughout, since TN-019 showed proportional
de-vigging distorts the very tail where a weak feature would look strongest.
"""
import math
import re
import sqlite3
import statistics as st
import unicodedata
from collections import defaultdict, deque
from datetime import date as DT
from pathlib import Path

DB = Path(__file__).resolve().parent / "tennis_ace.sqlite"
EPS = 1e-9


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", s.lower()).strip()


def ktml(n):
    p = [x for x in norm(n).split() if x]
    return "%s|%s" % (" ".join(p[1:]), p[0][:1]) if len(p) >= 2 else None


con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=60)
M = con.execute("""SELECT date, year, surface, player, opp, player_rank, opp_rank,
                          player_ht, opp_ht FROM ace_pm
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
    t = sum(p)
    return p[0] / t, p[1] / t


def price(d, w, l):
    kw, kl = ktml(w), ktml(l)
    if not kw or not kl:
        return None
    for dd, wo, lo in oh.get((kw, kl), []):
        try:
            if abs((DT.fromisoformat(dd) - DT.fromisoformat(d)).days) <= 4:
                return shin2(wo, lo)[0]
        except Exception:                                               # noqa: BLE001
            continue
    return None


K = 24.0
elo = defaultdict(lambda: 1500.0)
elo_s = defaultdict(lambda: defaultdict(lambda: 1500.0))
last10 = defaultdict(lambda: deque(maxlen=10))
lastdate = {}
recent = defaultdict(list)
h2h = defaultdict(lambda: [0, 0])
rows = []
for d, yr, surf, w, l, wr, lr, wht, lht in M:
    p = price(d, w, l)
    if p is not None and 0.01 < p < 0.99:
        f10w = (sum(last10[w]) / len(last10[w])) if len(last10[w]) >= 5 else None
        f10l = (sum(last10[l]) / len(last10[l])) if len(last10[l]) >= 5 else None
        ew, el = elo[w], elo[l]
        sw, sl = elo_s[surf][w], elo_s[surf][l]

        def rest(pl):
            if pl not in lastdate:
                return None
            return min((DT.fromisoformat(d) - DT.fromisoformat(lastdate[pl])).days, 30)

        def load(pl):
            return sum(1 for x in recent[pl]
                       if (DT.fromisoformat(d) - DT.fromisoformat(x)).days <= 14)

        hw, hl = h2h[(w, l)][0], h2h[(w, l)][1]
        feats = {}
        if f10w is not None and f10l is not None:
            feats["form_10"] = f10w - f10l
            feats["form_delta"] = (f10w - f10l) - ((ew - el) / 400.0)
        feats["surf_edge"] = (sw - ew) - (sl - el)
        rw, rl = rest(w), rest(l)
        if rw is not None and rl is not None:
            feats["rest_days"] = rw - rl
        feats["load_14"] = load(w) - load(l)
        if hw + hl >= 2:
            feats["h2h"] = hw / (hw + hl) - 0.5
        if wr and lr and wr > 0 and lr > 0:
            feats["rank_gap"] = math.log(lr / wr)
        if wht and lht:
            feats["ht_gap"] = (wht - lht) / 10.0
        rows.append((yr, p, feats))
    # ---- update AFTER predicting ----
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

print("priced matches with features: %d" % len(rows))
tr = [r for r in rows if r[0] <= 2023]
te = [r for r in rows if r[0] >= 2024]
print("train %d | test %d" % (len(tr), len(te)))


def rows_for(data, fname):
    """BOTH orientations per match. Fitting on winner-oriented rows only is degenerate: the
    outcome is 1 everywhere, so the intercept runs to infinity and every feature 'helps' by the
    whole log-loss. Emitting the mirror row (loser's view, y=0, negated feature) restores a real
    binary target."""
    out = []
    for _y, p, f in data:
        if fname not in f:
            continue
        x0 = math.log(p / (1 - p))
        out.append((x0, f[fname], 1.0))          # winner's view
        out.append((-x0, -f[fname], 0.0))        # loser's view - mirror image
    return out


def fit_logit(data, fname):
    """y ~ a + b*logit(pin) + c*feature, Newton. Returns (c, se_c, coefs)."""
    D = rows_for(data, fname)
    if len(D) < 800:
        return None
    X = [[1.0, x0, z] for x0, z, _yy in D]
    y = [yy for _x0, _z, yy in D]
    b = [0.0, 1.0, 0.0]
    for _ in range(40):
        g = [0.0, 0.0, 0.0]
        H = [[0.0] * 3 for _ in range(3)]
        for xi, yi in zip(X, y):
            z = sum(bb * xx for bb, xx in zip(b, xi))
            q = 1 / (1 + math.exp(-max(min(z, 30), -30)))
            w = q * (1 - q) + 1e-9
            for i in range(3):
                g[i] += (q - yi) * xi[i]
                for j in range(3):
                    H[i][j] += w * xi[i] * xi[j]
        try:
            import numpy as np
            step = np.linalg.solve(np.array(H), np.array(g))
        except Exception:                                               # noqa: BLE001
            return None
        b = [bb - ss for bb, ss in zip(b, step)]
        if max(abs(s) for s in step) < 1e-9:
            break
    import numpy as np
    cov = np.linalg.pinv(np.array(H))
    return b[2], math.sqrt(max(cov[2][2], 0)), b


print("\n" + "=" * 96)
print("DOES THE FACTOR ADD ANYTHING ON TOP OF PINNACLE?  (coefficient c, fitted 2015-2023)")
print("=" * 96)
print("   %-14s %8s %10s %10s %9s %14s" % ("factor", "n", "coef c", "SE", "t", "OOS delta LL"))
names = ["form_10", "form_delta", "surf_edge", "rest_days", "load_14", "h2h", "rank_gap", "ht_gap"]
for fn in names:
    r = fit_logit(tr, fn)
    if not r:
        print("   %-14s too few" % fn)
        continue
    c, se, b = r
    sub = rows_for(te, fn)
    if len(sub) < 400:
        print("   %-14s %8d %10.4f %10.4f %9.2f   test too small"
              % (fn, len(sub), c, se, c / se if se else 0))
        continue

    def nll(pred):
        t = 0.0
        for x0, z, yy in sub:
            q = pred(x0, z)
            q = min(max(q, EPS), 1 - EPS)
            t += -(yy * math.log(q) + (1 - yy) * math.log(1 - q))
        return t / len(sub)

    # baseline is PINNACLE ITSELF, untouched - not a refitted intercept/slope, which would
    # flatter the feature by also handing it a recalibration it did not earn.
    base = nll(lambda x0, z: 1 / (1 + math.exp(-x0)))
    withf = nll(lambda x0, z: 1 / (1 + math.exp(-(b[0] + b[1] * x0 + b[2] * z))))
    print("   %-14s %8d %10.4f %10.4f %9.2f %+14.5f%s"
          % (fn, len(sub) // 2, c, se, c / se if se else 0, withf - base,
             "  <- HELPS" if withf < base - 1e-5 else ""))
print()
print("   OOS delta LL is (with feature) minus (Pinnacle alone): NEGATIVE means the feature helps.")
print("   A large t with a positive delta is an in-sample coefficient that does not survive.")
