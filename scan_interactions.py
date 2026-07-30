"""Scan every golf-logical skill x condition interaction, with the discipline the count demands.

THE GOLF LOGIC BEING TESTED (mechanism first, then the prediction it implies):
  PRIOR RAIN -> SOFT GREENS.  Water held from yesterday is the mechanism, not today's total.
      soft greens HOLD approach shots      -> SG_APP / GIR should pay MORE
      soft fairways kill roll              -> DRIVE_DIST should pay MORE (course plays longer)
      receptive greens                     -> scoring easier, more birdies
  WIND.  Ball flight is disturbed.
      ball-striking (OTT/APP) should pay MORE; putting is unaffected in the air so should pay LESS
      and scoring should rise (already measured: -0.00515 birdie rate per km/h)
  COLD.  Dense air, ball flies shorter -> course plays longer -> DRIVE_DIST should pay MORE.
  HUMIDITY.  Humid air is LESS dense, so the ball flies slightly FARTHER — the opposite of the
      common intuition, which is why it is worth testing rather than assuming.

DISCIPLINE. ~50 interactions are scanned, so at p<0.05 roughly 2-3 will look real by chance, and
with n~35,000 even r=0.01 is "significant" while being worthless. So:
  * effect size (r) is reported, not p
  * anything interesting must PERSIST out of sample — fit on 2023-24, test on 2025-26
Everything measured today that failed did so at this second step, which is exactly its job.
"""
import math
import os
import sqlite3
import statistics as st

DB = os.path.expanduser("~/pga_interactions.sqlite")
SKILLS = ["SG_OTT", "SG_APP", "SG_ARG", "SG_PUTT", "DRIVE_DIST", "DRIVE_ACC", "GIR", "SCRAMBLE"]
CONDS = [("wind", "wind speed"), ("precip1", "rain YESTERDAY (soft)"),
         ("precip3", "rain prior 2-4 days"), ("tmax", "max temperature"),
         ("rh", "humidity")]


def z(vals):
    v = [x for x in vals if x is not None]
    if len(v) < 30:
        return None, None
    m, s = st.mean(v), st.pstdev(v)
    return m, (s or 1.0)


def corr(pairs):
    if len(pairs) < 200:
        return None, len(pairs)
    xs = [a for a, _ in pairs]
    ys = [b for _, b in pairs]
    mx, my = st.mean(xs), st.mean(ys)
    sx, sy = st.pstdev(xs), st.pstdev(ys)
    if not sx or not sy:
        return None, len(pairs)
    return (sum((a - mx) * (b - my) for a, b in pairs) / len(pairs) / (sx * sy)), len(pairs)


con = sqlite3.connect(DB)
cols = ["course", "year", "resid"] + [c for c, _ in CONDS] + SKILLS
rows = con.execute("SELECT %s FROM ix" % ",".join(cols)).fetchall()
con.close()
print("rows: %d" % len(rows))
idx = {c: i for i, c in enumerate(cols)}

# normalise conditions to z-scores WITHIN course, so "windy" means windy for THIS venue rather
# than for the tour — otherwise the interaction just re-discovers which courses are windy
bycourse = {}
for r in rows:
    bycourse.setdefault(r[idx["course"]], []).append(r)
norm = {}
for ck, rs in bycourse.items():
    for c, _lbl in CONDS:
        m, s = z([r[idx[c]] for r in rs])
        norm[(ck, c)] = (m, s)

print()
print("=== [0] SANITY: do the conditions move SCORING at all? (validates the weather data) ===")
print("    field-level effect on the residual's own spread is not the test; this checks that the")
print("    weather variables are real and varied before any interaction is believed")
for c, lbl in CONDS:
    v = [r[idx[c]] for r in rows if r[idx[c]] is not None]
    if len(v) < 200:
        print("    %-22s no data" % lbl)
        continue
    print("    %-22s n=%6d  mean %8.2f  sd %6.2f  range %.1f..%.1f"
          % (lbl, len(v), st.mean(v), st.pstdev(v), min(v), max(v)))

print()
print("=== [1] INTERACTION SCAN — skill x condition on the residual our model MISSES ===")
print("    r > 0 : the skill UNDERperforms its rating as the condition rises")
print("    r < 0 : the skill OUTperforms its rating as the condition rises (an exploitable edge)")
print()
print("    %-11s %-22s %8s %8s   %s" % ("skill", "condition", "r", "n", "flag"))
cands = []
for sk in SKILLS:
    for c, lbl in CONDS:
        pts = []
        for r in rows:
            cv, sv, rs = r[idx[c]], r[idx[sk]], r[idx["resid"]]
            if cv is None or sv is None or rs is None:
                continue
            m, s = norm.get((r[idx["course"]], c), (None, None))
            if m is None:
                continue
            pts.append((((cv - m) / s) * sv, rs))
        rr, n = corr(pts)
        if rr is None:
            continue
        flag = ""
        if abs(rr) >= 0.03:
            flag = "<- candidate"
            cands.append((sk, c, lbl, rr))
        print("    %-11s %-22s %+8.4f %8d   %s" % (sk, lbl, rr, n, flag))

print()
print("=== [2] OUT-OF-SAMPLE: do the candidates persist? fit 2023-24 -> test 2025-26 ===")
if not cands:
    print("    no interaction reached |r| >= 0.03. With n~35k that bar is already generous —")
    print("    nothing here is worth wiring in.")
else:
    for sk, c, lbl, rfull in sorted(cands, key=lambda x: -abs(x[3])):
        def sub(years):
            pts = []
            for r in rows:
                if r[idx["year"]] not in years:
                    continue
                cv, sv, rs = r[idx[c]], r[idx[sk]], r[idx["resid"]]
                if cv is None or sv is None or rs is None:
                    continue
                m, s = norm.get((r[idx["course"]], c), (None, None))
                if m is None:
                    continue
                pts.append((((cv - m) / s) * sv, rs))
            return corr(pts)
        r_early, n_e = sub({2023, 2024})
        r_late, n_l = sub({2025, 2026})
        ok = (r_early is not None and r_late is not None
              and r_early * r_late > 0 and abs(r_late) >= 0.02)
        print("    %-11s %-22s full %+.4f | 2023-24 %s | 2025-26 %s -> %s"
              % (sk, lbl, rfull,
                 ("%+.4f" % r_early) if r_early is not None else "n/a",
                 ("%+.4f" % r_late) if r_late is not None else "n/a",
                 "PERSISTS" if ok else "does NOT persist (sign flip or collapse)"))
