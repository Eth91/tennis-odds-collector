#!/usr/bin/env python3
"""Calibrate the live Elo against realised outcomes, and refuse to bet if it stays worse than fair.

The first working scan flagged 34 bets and EVERY top pick was an underdog at +24% to +43%. That is
not 34 opportunities, it is one property: our Elo is flatter than the market (backtest LL 0.629
against Pinnacle's 0.595), and a model that under-discriminates always "finds value" on longshots.
Deploying it unchanged would produce a forward ledger that loses in a way that teaches nothing,
because the loss would come from known miscalibration rather than from the market being right.

FIX: fit  logit(p_true) = a + b * logit(p_model)  on realised results, exactly the SHAPE_SLOPE
correction from the golf phase. b > 1 means the raw model is too flat and needs extremising. The
coefficients are fitted on history and saved, so the live scorer applies a calibration it earned
rather than a probability it merely computed.

REPORTED HONESTLY: the calibrated model's log-loss against the same matches, so we can see whether
calibration alone closes the gap to the market - and if it does not, that is the answer.
"""
import math
import pickle
import re
import sqlite3
import statistics as st
import unicodedata
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ADB = HERE / "tennis_ace.sqlite"
CFG = pickle.load(open(HERE / "ml_config.pkl", "rb"))
K, BLEND, BASE_S = CFG["K"], CFG["blend"], CFG["base"]


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", s.lower()).strip()


def pkey(name):
    t = [x for x in norm(name).split() if x]
    if not t:
        return ""
    if len(t) == 1:
        return t[0]
    if len(t[-1]) == 1:
        return "%s|%s" % (" ".join(t[:-1]), t[-1])
    return "%s|%s" % (" ".join(t[1:]), t[0][:1])


con = sqlite3.connect("file:%s?mode=ro" % ADB, uri=True, timeout=60)
res = con.execute("""SELECT date, surface, winner, loser, w_odds, l_odds FROM results_live
                     ORDER BY date""").fetchall()
con.close()
print("results: %d" % len(res))

elo = defaultdict(lambda: 1500.0)
elos = defaultdict(lambda: defaultdict(lambda: 1500.0))
seen = defaultdict(int)
rows = []
for d, surf, w, l, wo, lo in res:
    sf = surf if surf in BASE_S else "Hard"
    A, B = pkey(w), pkey(l)
    pe = 1.0 / (1.0 + 10 ** ((elo[B] - elo[A]) / 400.0))
    ps = 1.0 / (1.0 + 10 ** ((elos[sf][B] - elos[sf][A]) / 400.0))
    p = (1 - BLEND) * pe + BLEND * ps
    if seen[A] >= 20 and seen[B] >= 20:
        # ORIENT BY NAME SORT so the label is not derived from the feature
        first_is_w = A < B
        rows.append((d, p if first_is_w else 1 - p, 1.0 if first_is_w else 0.0,
                     # ORIENT THE MARKET THE SAME WAY AS THE LABEL. Storing P(winner wins) while
                     # the label is name-sort oriented made Pinnacle score 0.80 - worse than our
                     # Elo, which is impossible and was the tell.
                     (((1 / wo) / ((1 / wo) + (1 / lo))) if first_is_w
                      else (1 - (1 / wo) / ((1 / wo) + (1 / lo)))) if (wo and lo) else None,
                     first_is_w))
    elo[A] += K * (1 - pe)
    elo[B] -= K * (1 - pe)
    elos[sf][A] += K * (1 - ps)
    elos[sf][B] -= K * (1 - ps)
    seen[A] += 1
    seen[B] += 1
print("usable (both players >=20 matches): %d" % len(rows))

tr = [r for r in rows if r[0] < "2025-01-01"]
te = [r for r in rows if r[0] >= "2025-01-01"]
print("calibration fit on %d, checked on %d" % (len(tr), len(te)))


def lg(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


X = np.array([[1.0, lg(r[1])] for r in tr])
Y = np.array([r[2] for r in tr])
b = np.array([0.0, 1.0])
for _ in range(60):
    q = 1 / (1 + np.exp(-np.clip(X @ b, -30, 30)))
    H = (X * (q * (1 - q) + 1e-9)[:, None]).T @ X
    try:
        b = b - np.linalg.solve(H, X.T @ (q - Y))
    except np.linalg.LinAlgError:
        break
print("\ncalibration:  logit(p_true) = %.4f + %.4f * logit(p_model)" % (b[0], b[1]))
print("   slope %s 1 -> the raw model is %s"
      % (">" if b[1] > 1 else "<", "TOO FLAT and needs extremising" if b[1] > 1
         else "TOO CONFIDENT and needs damping"))

XT = np.array([[1.0, lg(r[1])] for r in te])
YT = np.array([r[2] for r in te])


def nll(p):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-(YT * np.log(p) + (1 - YT) * np.log(1 - p)).mean())


raw = nll(1 / (1 + np.exp(-XT[:, 1])))
cal = nll(1 / (1 + np.exp(-np.clip(XT @ b, -30, 30))))
mk = [r for r in te if r[3] is not None]
if mk:
    Pm = np.array([r[3] for r in mk])
    Ym = np.array([r[2] for r in mk])
    Pm = np.clip(Pm, 1e-9, 1 - 1e-9)
    mkt = float(-(Ym * np.log(Pm) + (1 - Ym) * np.log(1 - Pm)).mean())
else:
    mkt = float("nan")
print("\n2025+ held out:  raw model %.5f | CALIBRATED %.5f | market %.5f" % (raw, cal, mkt))
gap = raw - mkt
print("   calibration closes %s of the gap to the market"
      % (("%.1f%%" % (100 * (raw - cal) / gap)) if gap > 1e-9 else "n/a (model already better)"))
pickle.dump({"a": float(b[0]), "b": float(b[1])}, open(HERE / "ml_calib.pkl", "wb"))
print("\nsaved ml_calib.pkl")
if cal > mkt:
    print("\n   THE CALIBRATED MODEL IS STILL WORSE THAN THE MARKET (%.5f vs %.5f)." % (cal, mkt))
    print("   Any 'edge' it flags is therefore its remaining error, not the book's. A forward")
    print("   ledger built on it measures our miscalibration, not the market's.")
