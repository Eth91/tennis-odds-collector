#!/usr/bin/env python3
"""ACE MODEL v2 — moneyline-driven workload + a train-only bias correction.

v1 left two things on the table, both named in its own write-up:

  WORKLOAD  handing the model TRUE service points cut MAE from 2.9686 to 2.5724, so ~13% of all
            error was match-LENGTH uncertainty rather than serving. Length is exactly what a
            moneyline knows: a lopsided match is short, a close one is long.
  BIAS      the model ran 2-5% LOW on every surface. On a market that quotes only OVERS, a low
            bias points the wrong way on every single bet.

WORKLOAD, redesigned as length x style rather than one blended average:

    expected_service_points = expected_service_GAMES(moneyline, best_of) x points_per_service_game

Service games are a property of the MATCH - how long it goes - and points per service game are a
property of the PLAYER: a big server holds in four points, a grinder goes to deuce. Averaging both
players' historical service-point totals, as v1 did, blends those two very different things and
lets a short match with a grinder look like a long match with a server.

The moneyline enters ONLY through expected games, fitted on TRAIN by (best_of, |M-0.5|) bucket, so
the relationship is measured rather than assumed and cannot smuggle in anything about aces.

BIAS, corrected the way the games model in this project was: fit actual ~ a + b*pred on TRAIN and
apply the SAME two numbers to test. Fitting it on test would guarantee zero bias and prove nothing.

Rows without a joined price fall back to the v1 workload, and the moneyline A/B is reported on the
JOINED SUBSET ONLY so the comparison is like-for-like rather than a coverage artifact.
"""
import datetime as dt
import math
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
    "SELECT date, year, surface, best_of, player, opp, won, aces, svpt, sv_gms "
    "FROM ace_pm WHERE svpt>0 AND sv_gms>0 AND surface IS NOT NULL AND surface!='' "
    "ORDER BY date").fetchall()


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", s.lower()).strip()


def key_tml(name):
    p = [x for x in norm(name).split() if x]
    return "%s|%s" % (" ".join(p[1:]), p[0][:1]) if len(p) >= 2 else None


oh = defaultdict(list)
try:
    for d, wk, lk, wo, lo in con.execute("SELECT date, wkey, lkey, w_odds, l_odds FROM odds_hist"):
        oh[(wk, lk)].append((d, wo, lo))
except sqlite3.Error:
    print("NOTE: odds_hist not present - running without the moneyline")
con.close()
print("rows %d | priced pairs %d" % (len(rows), len(oh)))


def money(d, pl, op, won):
    """De-vigged P(this player wins). None when unjoinable."""
    kp, ko = key_tml(pl), key_tml(op)
    if not kp or not ko:
        return None
    cand = oh.get((kp, ko)) if won else oh.get((ko, kp))
    if not cand:
        return None
    for dd, wo, lo in cand:
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


base = {}
for s in {r[2] for r in rows}:
    v = [(r[7], r[8]) for r in rows if r[2] == s and r[1] <= 2024]
    if v:
        base[s] = sum(a for a, _ in v) / max(sum(p for _, p in v), 1)

# ---- expected SERVICE GAMES from (best_of, closeness), fitted on TRAIN only -----------------
gm_bucket = defaultdict(list)
gm_bo = defaultdict(list)
for d, yr, surf, bo, pl, op, won, aces, svpt, gms in rows:
    if yr > 2024:
        continue
    gm_bo[bo].append(gms)
    M = money(d, pl, op, won)
    if M is not None:
        gm_bucket[(bo, min(int(abs(M - 0.5) / 0.1), 4))].append(gms)
GM_BO = {bo: st.mean(v) for bo, v in gm_bo.items() if v}
GM_BK = {k: st.mean(v) for k, v in gm_bucket.items() if len(v) >= 30}
print("\nexpected SERVICE GAMES by best_of and closeness (train):")
for bo in sorted(GM_BO):
    cells = []
    for b in range(5):
        v = GM_BK.get((bo, b))
        cells.append("%.1f" % v if v else "  - ")
    print("   bo%d  overall %.1f  |  by |M-0.5|: 0-.1 %s  .1-.2 %s  .2-.3 %s  .3-.4 %s  .4+ %s"
          % (bo, GM_BO[bo], cells[0], cells[1], cells[2], cells[3], cells[4]))


def run(use_money):
    sv = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, None]))
    rt = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, None]))
    ppg = defaultdict(lambda: [0.0, 0.0])          # player -> [svpt, sv_gms] as-of
    load = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    tr, te = [], []
    for d, yr, surf, bo, pl, op, won, aces, svpt, gms in rows:
        b = base.get(surf)
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
        r_s = (sa + K_SHRINK * b) / (sp + K_SHRINK)
        r_r = (ra + K_SHRINK * b) / (rp + K_SHRINK)
        rate = r_s * r_r / b

        # The joined FLAG must be independent of whether the price is USED, or the v1 arm
        # filters to zero rows and the like-for-like comparison silently has no rows in it.
        M_avail = money(d, pl, op, won)
        M = M_avail if use_money else None
        pv, pn = ppg[pl]
        pts_per_gm = (pv / pn) if pn >= 30 else 6.2
        if M is not None:
            eg = GM_BK.get((bo, min(int(abs(M - 0.5) / 0.1), 4))) or GM_BO.get(bo, 12.0)
            exp_svpt = eg * pts_per_gm
        else:
            lp, ln = load[pl][bo]
            lo_, lon = load[op][bo]
            exp_svpt = (((lp / ln) if ln >= 3 else 0.0) * 0.5
                        + ((lo_ / lon) if lon >= 3 else 0.0) * 0.5) or (60.0 if bo == 3 else 100.0)
        rec = dict(y=yr, aces=aces, svpt=svpt, surf=surf, bo=bo, joined=(M_avail is not None),
                   pred=rate * exp_svpt, pred_actual_load=rate * svpt, exp_svpt=exp_svpt)
        (te if yr == TEST_YEAR else (tr if yr <= 2024 else [])).append(rec)
        for store, key in ((sv, pl), (rt, op)):
            A, P, last = store[key][surf]
            w = 0.5 ** (days(last, d) / HALF_LIFE) if last else 1.0
            store[key][surf] = [A * w + aces, P * w + svpt, d]
        ppg[pl][0] += svpt
        ppg[pl][1] += gms
        load[pl][bo][0] += svpt
        load[pl][bo][1] += 1
    return tr, te


def mae(v, k):
    return sum(abs(x["aces"] - x[k]) for x in v) / len(v) if v else float("nan")


def bias(v, k):
    return sum(x[k] - x["aces"] for x in v) / len(v) if v else float("nan")


tr_n, te_n = run(False)
tr_m, te_m = run(True)

print("\n" + "=" * 92)
print("A — DOES THE MONEYLINE IMPROVE WORKLOAD? (joined rows only, like-for-like)")
print("=" * 92)
jn = [x for x in te_n if x["joined"]]
jm = [x for x in te_m if x["joined"]]
print("   joined test rows: %d of %d (%.0f%%)" % (len(jm), len(te_m), 100 * len(jm) / len(te_m)))
if jm:
    print("   service-point MAE   v1 blended-history %.2f   vs   moneyline x style %.2f"
          % (sum(abs(x["svpt"] - x["exp_svpt"]) for x in jn) / len(jn),
             sum(abs(x["svpt"] - x["exp_svpt"]) for x in jm) / len(jm)))
    print("   ACE MAE             v1 %.4f   vs   v2 %.4f   -> %s"
          % (mae(jn, "pred"), mae(jm, "pred"),
             "MONEYLINE HELPS" if mae(jm, "pred") < mae(jn, "pred") else "no gain"))

print("\n" + "=" * 92)
print("B — BIAS CORRECTION, fitted on TRAIN ONLY")
print("=" * 92)
xs = [x["pred"] for x in tr_m]
ys = [x["aces"] for x in tr_m]
mx, my = st.mean(xs), st.mean(ys)
sxx = sum((x - mx) ** 2 for x in xs)
bt = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 1.0
al = my - bt * mx
print("   train fit:  actual = %.4f + %.4f * pred   (n=%d)" % (al, bt, len(tr_m)))
for x in te_m:
    x["pred_cal"] = al + bt * x["pred"]
print("   TEST bias (pred - actual):  before %+.4f   after %+.4f  aces/match"
      % (bias(te_m, "pred"), bias(te_m, "pred_cal")))
print("   TEST MAE:                   before %.4f    after %.4f"
      % (mae(te_m, "pred"), mae(te_m, "pred_cal")))
print("\n   bias by surface AFTER correction:")
for s in ("Grass", "Hard", "Clay"):
    ss = [x for x in te_m if x["surf"] == s]
    if len(ss) > 50:
        print("      %-7s n=%5d  actual %5.2f  pred %5.2f  bias %+.3f"
              % (s, len(ss), st.mean([x["aces"] for x in ss]),
                 st.mean([x["pred_cal"] for x in ss]), bias(ss, "pred_cal")))

print("\n" + "=" * 92)
print("C — FULL CHRONOLOGICAL BACKTEST, train <= 2024, test 2025")
print("=" * 92)
print("   %-42s %9s %10s" % ("model", "MAE", "bias"))
print("   %-42s %9.4f %+10.4f" % ("v1  no moneyline, no correction",
                                  mae(te_n, "pred"), bias(te_n, "pred")))
print("   %-42s %9.4f %+10.4f" % ("v2  moneyline workload",
                                  mae(te_m, "pred"), bias(te_m, "pred")))
print("   %-42s %9.4f %+10.4f" % ("v2  + bias correction  <- SHIPPABLE",
                                  mae(te_m, "pred_cal"), bias(te_m, "pred_cal")))
print("   %-42s %9.4f %+10.4f" % ("ceiling: rate x ACTUAL service points",
                                  mae(te_m, "pred_actual_load"), bias(te_m, "pred_actual_load")))
