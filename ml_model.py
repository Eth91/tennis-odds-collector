#!/usr/bin/env python3
"""BEST-EFFORT MONEYLINE MODEL: serve/return point model + tuned Elo, stacked. Chronological.

Three models, each a genuinely different view, then stacked:

  ELO        surface-blended, K and blend tuned on train. Compresses a career into one number.
  POINT      per-player serve strength and return strength, opponent-adjusted, run through the
             analytic point -> game -> set -> match recursion. Keeps the two halves of tennis
             separate, which Elo cannot: a huge server who cannot return is a different animal
             from a grinder with the same win rate, and they match up differently.
  STACK      logistic combination of the two, weights fitted on train only.

POINT MODEL, the core identity. For A serving against B:
    p_A = s_A + (S - o_B)
where s_A is A's own serve-points-won rate, o_B is the rate A's OPPONENTS win on serve against B
(so a good returner drags it down), and S is the surface baseline. If B is an exactly average
returner, o_B = S and p_A = s_A, which is the right null. Both inputs are decayed and
empirical-Bayes shrunk toward the surface baseline, because a player with 300 service points has a
rate that is mostly noise.

Match probability is then EXACT rather than simulated: game win from point win in closed form, set
by dynamic programming over (games, games, server) including a tiebreak, and match from sets.

Everything is accumulated in DATE + ROUND order - the ordering bug TN-028 exposed, where a final
could be replayed before its own first round and features saw matches a player had to win to reach.
Ratings update only AFTER a match is predicted.
"""
import math
import pickle
import re
import sqlite3
import statistics as st
import unicodedata
from collections import defaultdict
from datetime import date as DT
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DB = HERE / "tennis_ace.sqlite"
EPS = 1e-12
RND = {"R128": 1, "RR": 2, "R64": 2, "R32": 3, "R16": 4, "QF": 5, "SF": 6, "BR": 6, "F": 7}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", s.lower()).strip()


def ktml(n_):
    p = [x for x in norm(n_).split() if x]
    return "%s|%s" % (" ".join(p[1:]), p[0][:1]) if len(p) >= 2 else None


# ---------- exact point -> match ---------------------------------------------------------------
def game_win(p):
    """P(win a service game) given P(win a point on serve). Closed form with deuce."""
    p = min(max(p, 1e-6), 1 - 1e-6)
    q = 1 - p
    d = p * p / (p * p + q * q) if (p * p + q * q) > 0 else 0.5     # win from deuce
    # win to love / 15 / 30, plus reaching deuce (3-3) and taking it
    return (p ** 4
            + 4 * p ** 4 * q
            + 10 * p ** 4 * q * q
            + 20 * p ** 3 * q ** 3 * d)


def tb_win(pa, pb, target=7):
    """Tiebreak by DP over (a, b, server-index), with the endless deuce phase in CLOSED FORM.

    A tiebreak past 6-6 can in principle run forever, and recursing into it blows the stack (it
    did: 480 frames deep before RecursionError). Beyond 6-6 the state is memoryless - each player
    serves one of every two points - so the two-point cycle has an exact solution:
        P(win the cycle) = x / (x + y)  with x = P(win both), y = P(lose both)
    which is the same trick the deuce term in game_win uses.
    """
    from functools import lru_cache
    pw = pa                    # A wins a point on A's serve
    pl = 1 - pb                # A wins a point on B's serve
    x = pw * pl                # A takes both points of a cycle
    y = (1 - pw) * (1 - pl)    # B takes both
    deuce = x / (x + y) if (x + y) > 1e-12 else 0.5

    @lru_cache(maxsize=None)
    def f(a, b, n):
        if a >= target and a - b >= 2:
            return 1.0
        if b >= target and b - a >= 2:
            return 0.0
        if a >= 6 and b >= 6 and a == b:
            return deuce                       # endless phase, solved not recursed
        if a > 20 or b > 20:
            return 1.0 if a > b else 0.0       # hard stop; unreachable in practice
        srv_a = (((n + 1) // 2) % 2) == 0
        p = pw if srv_a else pl
        return p * f(a + 1, b, n + 1) + (1 - p) * f(a, b + 1, n + 1)
    return f(0, 0, 0)


def set_win(pa, pb):
    """P(A wins a set), DP over games with A serving first (averaged over who serves first)."""
    ha, hb = game_win(pa), game_win(pb)
    from functools import lru_cache

    def solve(first_a):
        @lru_cache(maxsize=None)
        def f(a, b, srv_a):
            if a >= 6 and a - b >= 2:
                return 1.0
            if b >= 6 and b - a >= 2:
                return 0.0
            if a == 6 and b == 6:
                return tb_win(pa, pb)
            if a == 7 or b == 7:
                return 1.0 if a > b else 0.0
            p = ha if srv_a else (1 - hb)
            return p * f(a + 1, b, not srv_a) + (1 - p) * f(a, b + 1, not srv_a)
        return f(0, 0, first_a)
    return 0.5 * solve(True) + 0.5 * solve(False)


def match_win(pa, pb, bo):
    s = set_win(pa, pb)
    if bo == 5:
        return s ** 3 * (1 + 3 * (1 - s) + 6 * (1 - s) ** 2)
    return s * s * (3 - 2 * s)


# ---------- data ------------------------------------------------------------------------------
con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=60)
M = con.execute("""SELECT date, year, surface, best_of, round, player, opp, won,
                          svpt, first_won, second_won, o_svpt, o_first_won, o_second_won
                   FROM srv_pm WHERE first_won IS NOT NULL AND svpt>0 AND o_svpt>0
                     AND surface IS NOT NULL AND surface!='' AND won=1""").fetchall()
M.sort(key=lambda r: (r[0], RND.get(str(r[4]), 3)))
oh = defaultdict(list)
for d, wk, lk, wo, lo in con.execute("SELECT date, wkey, lkey, w_odds, l_odds FROM odds_hist"):
    oh[(wk, lk)].append((d, wo, lo))
con.close()
print("matches: %d | priced pairs: %d" % (len(M), len(oh)))


def shin2(o1, o2):
    q = [1.0 / o1, 1.0 / o2]
    R = sum(q)
    lo, hi = 0.0, 0.99
    for _ in range(90):
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


BASE_S = {}
for s in {r[2] for r in M}:
    v = [(r[9] + r[10], r[8]) for r in M if r[2] == s and r[1] <= 2023]
    if v:
        BASE_S[s] = sum(a for a, _ in v) / max(sum(b for _, b in v), 1)
print("surface serve baselines (train):", {k: round(v, 4) for k, v in BASE_S.items()})


def days(a, b):
    return ((int(b[:4]) - int(a[:4])) * 365.25 + (int(b[5:7]) - int(a[5:7])) * 30.44
            + (int(b[8:10]) - int(a[8:10])))


def run(K, blend, HL, KSH):
    elo = defaultdict(lambda: 1500.0)
    elos = defaultdict(lambda: defaultdict(lambda: 1500.0))
    srv = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, None]))   # own serve won/pts
    ret = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, None]))   # opp serve won/pts vs me
    out = []
    for d, yr, surf, bo, rnd, w, l, _won, sv, f1, f2, osv, of1, of2 in M:
        S = BASE_S.get(surf)
        if not S:
            continue
        pe = 1.0 / (1.0 + 10 ** ((elo[l] - elo[w]) / 400.0))
        ps = 1.0 / (1.0 + 10 ** ((elos[surf][l] - elos[surf][w]) / 400.0))
        p_elo = (1 - blend) * pe + blend * ps

        def dec(store, key):
            a, b, last = store[key][surf]
            if last is None:
                return 0.0, 0.0
            wgt = 0.5 ** (days(last, d) / HL)
            return a * wgt, b * wgt

        sw_a, sp_a = dec(srv, w)
        sw_b, sp_b = dec(srv, l)
        rw_a, rp_a = dec(ret, w)
        rw_b, rp_b = dec(ret, l)
        s_a = (sw_a + KSH * S) / (sp_a + KSH)
        s_b = (sw_b + KSH * S) / (sp_b + KSH)
        o_a = (rw_a + KSH * S) / (rp_a + KSH)     # how well opponents serve against A
        o_b = (rw_b + KSH * S) / (rp_b + KSH)
        pa = min(max(s_a + (S - o_b), 0.35), 0.85)
        pb = min(max(s_b + (S - o_a), 0.35), 0.85)
        p_pt = match_win(pa, pb, int(bo or 3))
        pin = price(d, w, l)
        out.append((yr, p_elo, p_pt, pin))
        # ---- update AFTER predicting ----
        elo[w] += K * (1 - pe)
        elo[l] -= K * (1 - pe)
        elos[surf][w] += K * (1 - ps)
        elos[surf][l] -= K * (1 - ps)
        for store, key, num, den in ((srv, w, f1 + f2, sv), (srv, l, of1 + of2, osv),
                                     (ret, l, f1 + f2, sv), (ret, w, of1 + of2, osv)):
            A, B, last = store[key][surf]
            wgt = 0.5 ** (days(last, d) / HL) if last else 1.0
            store[key][surf] = [A * wgt + num, B * wgt + den, d]
    return out


def ll_of(rows, idx):
    v = [r[idx] for r in rows if r[idx] is not None]
    return -sum(math.log(max(min(x, 1 - 1e-9), 1e-9)) for x in v) / len(v)


print("\n" + "=" * 88)
print("TUNE on 2015-2023 (log-loss of P(actual winner wins); lower is better)")
print("=" * 88)
best = None
for K in (16.0, 24.0, 32.0):
    for blend in (0.3, 0.5, 0.7):
        rows = run(K, blend, 540.0, 400.0)
        tr = [r for r in rows if r[0] <= 2023]
        v = ll_of(tr, 1)
        if best is None or v < best[0]:
            best = (v, K, blend)
        print("   K=%-5.0f surfaceBlend=%.1f   Elo LL %.5f" % (K, blend, v))
print("   -> best Elo config: K=%.0f blend=%.1f (LL %.5f)" % (best[1], best[2], best[0]))

print("\n   point-model shrinkage / half-life:")
bestp = None
for HL in (365.0, 730.0):
    for KSH in (200.0, 600.0):
        rows = run(best[1], best[2], HL, KSH)
        tr = [r for r in rows if r[0] <= 2023]
        v = ll_of(tr, 2)
        if bestp is None or v < bestp[0]:
            bestp = (v, HL, KSH)
        print("      half-life %4.0fd  k %4.0f   POINT LL %.5f" % (HL, KSH, v))
print("   -> best point config: HL=%.0f k=%.0f (LL %.5f)" % (bestp[1], bestp[2], bestp[0]))

rows = run(best[1], best[2], bestp[1], bestp[2])
pickle.dump(dict(K=best[1], blend=best[2], HL=bestp[1], KSH=bestp[2], base=BASE_S),
            open(HERE / "ml_config.pkl", "wb"))
tr = [r for r in rows if r[0] <= 2023]
te = [r for r in rows if r[0] >= 2024]
trp = [r for r in tr if r[3] is not None]
tep = [r for r in te if r[3] is not None]
print("\n" + "=" * 88)
print("HELD-OUT 2024-2025 (matches with a Pinnacle price: %d)" % len(tep))
print("=" * 88)
print("   %-26s %10s" % ("model", "log-loss"))
print("   %-26s %10.5f" % ("Elo (tuned)", ll_of(tep, 1)))
print("   %-26s %10.5f" % ("POINT model", ll_of(tep, 2)))
print("   %-26s %10.5f" % ("Pinnacle (Shin)", ll_of(tep, 3)))


def lg(p):
    return math.log(max(min(p, 1 - 1e-9), 1e-9) / (1 - max(min(p, 1 - 1e-9), 1e-9)))


# stack Elo+point on train, then see if it adds to Pinnacle
X = np.array([[1.0, lg(r[1]), lg(r[2])] for r in trp])
Y = np.ones(len(trp))
Xm = np.vstack([X, np.column_stack([np.ones(len(trp)), -X[:, 1], -X[:, 2]])])
Ym = np.concatenate([Y, np.zeros(len(trp))])
b = np.zeros(3)
for _ in range(60):
    q = 1 / (1 + np.exp(-np.clip(Xm @ b, -30, 30)))
    H = (Xm * (q * (1 - q) + 1e-9)[:, None]).T @ Xm
    try:
        b = b - np.linalg.solve(H, Xm.T @ (q - Ym))
    except np.linalg.LinAlgError:
        break
print("\n   stack weights (train): intercept %.3f  Elo %.3f  point %.3f" % (b[0], b[1], b[2]))
stack_te = [1 / (1 + math.exp(-np.clip(b[0] + b[1] * lg(r[1]) + b[2] * lg(r[2]), -30, 30)))
            for r in tep]
print("   %-26s %10.5f" % ("STACK (Elo+point)", -sum(math.log(max(x, 1e-9)) for x in stack_te) / len(stack_te)))

print("\n" + "=" * 88)
print("THE ONLY QUESTION THAT MATTERS: does the stack ADD to Pinnacle?")
print("=" * 88)
Xs = np.array([[1.0, lg(r[3]), lg(1 / (1 + math.exp(-np.clip(b[0] + b[1] * lg(r[1]) + b[2] * lg(r[2]), -30, 30))))] for r in trp])
Xs2 = np.vstack([Xs, np.column_stack([np.ones(len(trp)), -Xs[:, 1], -Xs[:, 2]])])
bb = np.zeros(3)
bb[1] = 1.0
for _ in range(60):
    q = 1 / (1 + np.exp(-np.clip(Xs2 @ bb, -30, 30)))
    H = (Xs2 * (q * (1 - q) + 1e-9)[:, None]).T @ Xs2
    try:
        bb = bb - np.linalg.solve(H, Xs2.T @ (q - np.concatenate([np.ones(len(trp)), np.zeros(len(trp))])))
    except np.linalg.LinAlgError:
        break
print("   weight on Pinnacle %.4f | weight on OUR STACK %.4f" % (bb[1], bb[2]))
blend_te = [1 / (1 + math.exp(-np.clip(bb[0] + bb[1] * lg(r[3]) + bb[2] * lg(s), -30, 30)))
            for r, s in zip(tep, stack_te)]
print("   held-out: Pinnacle %.5f | Pinnacle+stack %.5f | delta %+.5f"
      % (ll_of(tep, 3), -sum(math.log(max(x, 1e-9)) for x in blend_te) / len(blend_te),
         -sum(math.log(max(x, 1e-9)) for x in blend_te) / len(blend_te) - ll_of(tep, 3)))
