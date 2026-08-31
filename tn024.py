#!/usr/bin/env python3
"""TN-024 — is there HEADROOM in the moneyline model? The blend test.

"Can our model beat Pinnacle" is the wrong question and the answer has been no for three phases.
The useful question is whether a model carries ANY INFORMATION PINNACLE LACKS, and that is a
different thing: a model can be strictly worse standalone and still improve a sharp price if its
errors are uncorrelated with the book's.

The test is a blend in LOG-ODDS space, weight fitted on TRAIN and applied to a held-out period:

    logit(p_blend) = (1 - w) * logit(p_pinnacle) + w * logit(p_elo)

    w -> 0 on train   the model adds nothing Pinnacle does not already have. No headroom.
    w > 0 AND the holdout log-loss improves   there is real incremental information, and the size
                                              of the gain bounds how much headroom exists.

Elo is built chronologically from match results with a surface term, updating only AFTER each match
is predicted, so nothing leaks. Pinnacle probabilities are SHIN-devigged, since TN-019 showed
proportional de-vigging distorts exactly the longshot end where a weak model looks best.

TRAIN 2015-2023, TEST 2024-2025. The test period is never used to fit the weight.
"""
import math
import re
import sqlite3
import statistics as st
import unicodedata
from collections import defaultdict
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
matches = con.execute("""SELECT date, year, surface, player, opp FROM ace_pm
                         WHERE won=1 AND surface IS NOT NULL AND surface!='' ORDER BY date""").fetchall()
oh = defaultdict(list)
for d, wk, lk, wo, lo in con.execute("SELECT date, wkey, lkey, w_odds, l_odds FROM odds_hist"):
    oh[(wk, lk)].append((d, wo, lo))
con.close()
print("matches (winner rows): %d | priced pairs: %d" % (len(matches), len(oh)))


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
    from datetime import date as DT
    for dd, wo, lo in oh.get((kw, kl), []):
        try:
            if abs((DT.fromisoformat(dd) - DT.fromisoformat(d)).days) <= 4:
                a, _b = shin2(wo, lo)
                return a                      # SHIN P(winner wins), i.e. the realised outcome
        except Exception:                     # noqa: BLE001
            continue
    return None


K = 24.0
BASE = 1500.0
elo = defaultdict(lambda: BASE)
elo_s = defaultdict(lambda: defaultdict(lambda: BASE))
rows = []
for d, yr, surf, w, l in matches:
    ew, el = elo[w], elo[l]
    p_elo = 1.0 / (1.0 + 10 ** ((el - ew) / 400.0))
    sw, sl = elo_s[surf][w], elo_s[surf][l]
    p_es = 1.0 / (1.0 + 10 ** ((sl - sw) / 400.0))
    p_mix = 0.5 * p_elo + 0.5 * p_es          # overall + surface Elo, the prior project's design
    pin = price(d, w, l)
    if pin is not None and 0.01 < pin < 0.99:
        rows.append((yr, pin, min(max(p_mix, 0.01), 0.99)))
    # update AFTER predicting
    elo[w] = ew + K * (1 - p_elo)
    elo[l] = el - K * (1 - p_elo)
    elo_s[surf][w] = sw + K * (1 - p_es)
    elo_s[surf][l] = sl - K * (1 - p_es)

print("matches with BOTH an Elo prediction and a Shin-devigged Pinnacle price: %d" % len(rows))
tr = [r for r in rows if r[0] <= 2023]
te = [r for r in rows if r[0] >= 2024]
print("train %d (2015-2023)  |  test %d (2024-2025)" % (len(tr), len(te)))


def lg(p):
    return math.log(p / (1 - p))


def ll(pairs, w):
    tot = 0.0
    for _y, pin, pe in pairs:
        z = (1 - w) * lg(pin) + w * lg(pe)
        p = 1 / (1 + math.exp(-z))
        tot += -math.log(max(p, EPS))          # outcome is always 1 (winner-oriented rows)
    return tot / len(pairs)


print("\n" + "=" * 84)
print("BLEND WEIGHT FITTED ON TRAIN (2015-2023)")
print("=" * 84)
print("   %-10s %12s" % ("weight", "train LL"))
best = None
for w in (0.0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50):
    v = ll(tr, w)
    if best is None or v < best[1]:
        best = (w, v)
    print("   %-10.2f %12.5f%s" % (w, v, "   <-" if best[0] == w else ""))
print("   -> optimal train weight on the model: %.2f" % best[0])

print("\n" + "=" * 84)
print("HELD-OUT 2024-2025")
print("=" * 84)
l0 = ll(te, 0.0)
lb = ll(te, best[0])
print("   Pinnacle alone            log-loss %.5f" % l0)
print("   blend at train weight %.2f log-loss %.5f   delta %+.5f" % (best[0], lb, lb - l0))
print("   Elo alone                 log-loss %.5f" % ll(te, 1.0))
print()
acc_p = sum(1 for _y, pin, pe in te if pin > 0.5) / len(te)
acc_e = sum(1 for _y, pin, pe in te if pe > 0.5) / len(te)
print("   winner-picking accuracy:  Pinnacle %.3f   Elo %.3f" % (acc_p, acc_e))
print()
if best[0] <= 0.02 or lb >= l0:
    print("   -> NO HEADROOM. The optimal weight on the model is ~0, or the blend does not improve")
    print("      the held-out log-loss. Pinnacle already contains whatever the model knows.")
else:
    print("   -> HEADROOM EXISTS: weight %.2f improves held-out log-loss by %.5f. That gain bounds"
          % (best[0], l0 - lb))
    print("      how much a better model could be worth, and it is the whole budget available.")
