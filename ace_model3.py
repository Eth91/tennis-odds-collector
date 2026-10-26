#!/usr/bin/env python3
"""ACE MODEL v3 — a YEAR TERM for the residual bias. Extrapolated, never peeked at.

v2 still ran -0.10 aces LOW, and negative on all three surfaces at once. A bias with the same sign
everywhere is not a surface problem; it is a TIME problem. A decayed average with a 540-day
half-life sits, by construction, roughly a year behind the series it is averaging - so if ace rates
are drifting upward, every prediction inherits a stale level.

THE FIX MUST EXTRAPOLATE, NOT AVERAGE. Using the test year's own baseline would erase the bias and
prove nothing, because that number is not knowable on the morning of the match. Instead the yearly
surface baseline is regressed on year using TRAIN YEARS ONLY and projected FORWARD to the year
being predicted - exactly the information a forecaster standing in January 2025 actually has.

    year_multiplier(Y) = projected_baseline(surface, Y) / decayed_baseline_level
applied to the rate. If ace rates are flat the slope comes out ~0 and the term does nothing, which
is the honest null.
"""
import datetime as dt
import re
import sqlite3
import statistics as st
import unicodedata
from collections import defaultdict
from pathlib import Path

DB = Path(__file__).resolve().parent / "tennis_ace.sqlite"
TEST_YEAR = 2025
K_SHRINK = 200.0
HALF_LIFE = 540.0

con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=60)
rows = con.execute(
    "SELECT date, year, surface, best_of, player, opp, won, aces, svpt, sv_gms FROM ace_pm "
    "WHERE svpt>0 AND sv_gms>0 AND surface IS NOT NULL AND surface!='' ORDER BY date").fetchall()


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", s.lower()).strip()


def ktml(n):
    p = [x for x in norm(n).split() if x]
    return "%s|%s" % (" ".join(p[1:]), p[0][:1]) if len(p) >= 2 else None


oh = defaultdict(list)
for d, wk, lk, wo, lo in con.execute("SELECT date, wkey, lkey, w_odds, l_odds FROM odds_hist"):
    oh[(wk, lk)].append((d, wo, lo))
con.close()


def money(d, pl, op, won):
    kp, ko = ktml(pl), ktml(op)
    if not kp or not ko:
        return None
    for dd, wo, lo in (oh.get((kp, ko)) if won else oh.get((ko, kp))) or []:
        try:
            if abs((dt.date.fromisoformat(dd) - dt.date.fromisoformat(d)).days) <= 4:
                pw = (1 / wo) / ((1 / wo) + (1 / lo))
                return pw if won else 1 - pw
        except Exception:                                               # noqa: BLE001
            continue
    return None


def days(a, b):
    return ((int(b[:4]) - int(a[:4])) * 365.25 + (int(b[5:7]) - int(a[5:7])) * 30.44
            + (int(b[8:10]) - int(a[8:10])))


# ---- IS THERE A TREND AT ALL? measured on train years only ---------------------------------
yb = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
for d, yr, surf, bo, pl, op, won, aces, svpt, gms in rows:
    if yr <= 2024:
        yb[surf][yr][0] += aces
        yb[surf][yr][1] += svpt
print("=" * 90)
print("ACE RATE PER SERVICE POINT BY YEAR (train only) — is the bias a trend?")
print("=" * 90)
slope = {}
for surf in sorted(yb):
    pts = sorted((y, a / p) for y, (a, p) in yb[surf].items() if p > 5000)
    if len(pts) < 5:
        continue
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    slope[surf] = (b, my, mx)
    print("   %-7s %s" % (surf, "  ".join("%d:%.4f" % p for p in pts)))
    print("           slope %+.6f per year  (%.2f%% of the mean rate per year)"
          % (b, 100 * b / my if my else 0))


def base_for(surf, year):
    """Baseline PROJECTED to `year` from train years only. Never reads the year it predicts."""
    if surf not in slope:
        return None
    b, my, mx = slope[surf]
    return my + b * (year - mx)


base_flat = {}
for s in {r[2] for r in rows}:
    v = [(r[7], r[8]) for r in rows if r[2] == s and r[1] <= 2024]
    if v:
        base_flat[s] = sum(a for a, _ in v) / max(sum(p for _, p in v), 1)

gm_bucket = defaultdict(list)
gm_bo = defaultdict(list)
for d, yr, surf, bo, pl, op, won, aces, svpt, gms in rows:
    if yr > 2024:
        continue
    gm_bo[bo].append(gms)
    M = money(d, pl, op, won)
    if M is not None:
        gm_bucket[(bo, min(int(abs(M - 0.5) / 0.1), 4))].append(gms)
GM_BO = {k: st.mean(v) for k, v in gm_bo.items() if v}
GM_BK = {k: st.mean(v) for k, v in gm_bucket.items() if len(v) >= 30}


def run(use_year):
    sv = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, None]))
    rt = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, None]))
    ppg = defaultdict(lambda: [0.0, 0.0])
    tr, te = [], []
    for d, yr, surf, bo, pl, op, won, aces, svpt, gms in rows:
        b = base_flat.get(surf)
        if not b:
            continue

        def dec(store, key):
            a, p, last = store[key][surf]
            if last is None:
                return 0.0, 0.0
            w = 0.5 ** (days(last, d) / HALF_LIFE)
            return a * w, p * w

        sa, sp = dec(sv, pl)
        ra, rp = dec(rt, op)
        rate = ((sa + K_SHRINK * b) / (sp + K_SHRINK)) * ((ra + K_SHRINK * b) / (rp + K_SHRINK)) / b
        if use_year:
            proj = base_for(surf, yr)
            if proj and b:
                rate *= (proj / b)
        M = money(d, pl, op, won)
        pv, pn = ppg[pl]
        ppgm = (pv / pn) if pn >= 30 else 6.2
        eg = (GM_BK.get((bo, min(int(abs(M - 0.5) / 0.1), 4))) if M is not None else None) \
            or GM_BO.get(bo, 12.0)
        rec = dict(y=yr, aces=aces, svpt=svpt, surf=surf, pred=rate * eg * ppgm)
        (te if yr == TEST_YEAR else (tr if yr <= 2024 else [])).append(rec)
        for store, key in ((sv, pl), (rt, op)):
            A, P, last = store[key][surf]
            w = 0.5 ** (days(last, d) / HALF_LIFE) if last else 1.0
            store[key][surf] = [A * w + aces, P * w + svpt, d]
        ppg[pl][0] += svpt
        ppg[pl][1] += gms
    return tr, te


def mae(v, k):
    return sum(abs(x["aces"] - x[k]) for x in v) / len(v)


def bias(v, k):
    return sum(x[k] - x["aces"] for x in v) / len(v)


def calibrate(tr, te):
    xs = [x["pred"] for x in tr]
    ys = [x["aces"] for x in tr]
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 1.0
    a = my - b * mx
    for x in te:
        x["cal"] = a + b * x["pred"]
    return a, b


print("\n" + "=" * 90)
print("CHRONOLOGICAL BACKTEST, train <= 2024, test 2025")
print("=" * 90)
print("   %-46s %9s %10s" % ("model", "MAE", "bias"))
res = {}
for uy, lbl in ((False, "v2  no year term"), (True, "v3  + YEAR TERM (extrapolated)")):
    tr, te = run(uy)
    a, b = calibrate(tr, te)
    res[uy] = te
    print("   %-46s %9.4f %+10.4f" % (lbl, mae(te, "pred"), bias(te, "pred")))
    print("   %-46s %9.4f %+10.4f" % ("      + bias correction", mae(te, "cal"), bias(te, "cal")))
te3 = res[True]
print("\n   v3 residual bias by surface (after correction):")
for s in ("Grass", "Hard", "Clay"):
    ss = [x for x in te3 if x["surf"] == s]
    if len(ss) > 50:
        print("      %-7s n=%5d  actual %5.2f  pred %5.2f  bias %+.3f"
              % (s, len(ss), st.mean([x["aces"] for x in ss]),
                 st.mean([x["cal"] for x in ss]), bias(ss, "cal")))
