"""RHO, with the two confounds the first test exposed removed.

Test 1 used 72-hole totals and implied RHO = -0.065, i.e. rounds ANTI-correlated. Two reasons,
both artefacts rather than golf:

  CUT SELECTION  only players who made the cut have four rounds, and conditioning on a good
                 36-hole total truncates the distribution, compressing the spread of totals.
                 Rounds 1-2 are played by everybody, so the 36-hole total is selection-free.

  WAVE FLIP      a player who tees off in the morning for round 1 usually tees off in the
                 afternoon for round 2. Since the two waves genuinely play differently (we
                 measured 0.67 strokes on average), that flip induces NEGATIVE correlation
                 between rounds 1 and 2 which has nothing to do with the player's form.

So RHO is estimated three ways: from selection-free 36-hole totals, from raw round-pair
correlations, and from SAME-WAVE pairs only — the last isolating genuine player-week form,
which is what RHO is supposed to mean now that the wave is modelled separately.
"""
import math
import sqlite3
import statistics as st
from collections import defaultdict

import pga_ruler as RU

try:
    import pga_wave as W
    HAVE_WAVE = True
except Exception:                                                   # noqa: BLE001
    HAVE_WAVE = False

con = sqlite3.connect(RU.DB)
evs = con.execute("SELECT event_id, MIN(date) d, event FROM rounds GROUP BY event_id "
                  "HAVING d >= '2024-01-01' ORDER BY d").fetchall()
con.close()
rows_all = RU.all_rows()

pairs_raw = []          # (r_i, r_j) residuals, same player same event, i<j
pairs_same = []         # same wave
pairs_opp = []          # opposite wave
t36 = []                # selection-free 36-hole residuals
per_round = []

# tee sheet lookup, keyed by orchestrator tid -> {rnd: {player: wave}}
wave_by_ev = {}
if HAVE_WAVE:
    con = sqlite3.connect(W.TEEDB)
    try:
        tt = con.execute("SELECT tid, tname, rnd, player, tee_ms FROM tee_sheet").fetchall()
    except Exception:                                               # noqa: BLE001
        tt = []
    con.close()
    grp = defaultdict(lambda: defaultdict(dict))
    for tid, tname, rnd, pl, ms in tt:
        grp[str(tname or "").lower()][rnd][pl] = ms
    for nm, by_rnd in grp.items():
        out = {}
        for rnd, d in by_rnd.items():
            if len(d) >= 40:
                med = st.median(d.values())
                out[rnd] = {p: ("pm" if m > med else "am") for p, m in d.items()}
        if out:
            wave_by_ev[nm] = out

for eid, d0, evn in evs:
    con = sqlite3.connect(RU.DB)
    rr = con.execute("SELECT player, rnd, score FROM rounds WHERE event_id=? AND score>0",
                     (eid,)).fetchall()
    con.close()
    by_rnd = defaultdict(list)
    for pl, rnd, sc in rr:
        by_rnd[rnd].append((pl, sc))
    fm = {r: st.mean(s for _p, s in v) for r, v in by_rnd.items() if len(v) >= 20}
    if 1 not in fm or 2 not in fm:
        continue
    R, _ = RU.fit(asof=d0, rows=rows_all)
    Rn = {RU.norm(k): v for k, v in R.items()}
    got = defaultdict(dict)
    for pl, rnd, sc in rr:
        if rnd in fm:
            got[RU.norm(pl)][rnd] = sc - fm[rnd]
    wv = None
    key = str(evn or "").lower()
    for nm, w in wave_by_ev.items():
        if nm and (nm[:14] in key or key[:14] in nm):
            wv = w
            break
    for pl, d in got.items():
        r = Rn.get(pl)
        if not r:
            continue
        rt = r[0]
        for rnd, v in d.items():
            per_round.append(v - rt)
        if 1 in d and 2 in d:
            t36.append(d[1] + d[2] - 2 * rt)
        ks = sorted(d)
        for i in range(len(ks)):
            for j in range(i + 1, len(ks)):
                a, b = d[ks[i]] - rt, d[ks[j]] - rt
                pairs_raw.append((a, b))
                if wv:
                    wa = (wv.get(ks[i]) or {}).get(pl)
                    wb = (wv.get(ks[j]) or {}).get(pl)
                    if wa and wb:
                        (pairs_same if wa == wb else pairs_opp).append((a, b))


def corr(ps):
    if len(ps) < 200:
        return None, len(ps)
    xa = [p[0] for p in ps]
    xb = [p[1] for p in ps]
    ma, mb = st.mean(xa), st.mean(xb)
    sa, sb = st.pstdev(xa), st.pstdev(xb)
    if not sa or not sb:
        return None, len(ps)
    c = sum((x - ma) * (y - mb) for x, y in ps) / len(ps) / (sa * sb)
    return c, len(ps)


sig2 = st.pvariance(per_round)
print("2024-26: %d single rounds, %d round-pairs, %d selection-free 36-hole totals"
      % (len(per_round), len(pairs_raw), len(t36)))
print("per-round residual variance sig^2 = %.3f (sd %.3f)" % (sig2, math.sqrt(sig2)))
print()

print("[A] SELECTION-FREE 36-HOLE TOTAL (rounds 1-2, everybody plays them)")
v36 = st.pvariance(t36)
print("    observed Var(36-hole residual) = %.2f" % v36)
for rho in (0.0, 0.055, 0.15, 0.25):
    pv = 4 * rho * sig2 + 2 * (1 - rho) * sig2
    print("      RHO %.3f predicts %.2f  (%+.2f)%s"
          % (rho, pv, pv - v36, "  <- old assumed" if rho == 0.25 else ""))
implied36 = (v36 - 2 * sig2) / (2 * sig2)
print("    => RHO implied by 36-hole spread = %+.3f" % implied36)
print()

print("[B] RAW ROUND-PAIR CORRELATION (all pairs, wave flip included)")
c, n = corr(pairs_raw)
print("    r = %s on n=%d pairs   -> RHO_effective = %s"
      % (("%+.4f" % c) if c is not None else "n/a", n,
         ("%+.3f" % c) if c is not None else "n/a"))
print()

print("[C] SAME-WAVE vs OPPOSITE-WAVE (isolates real form from the tee-window flip)")
cs, ns = corr(pairs_same)
co, no = corr(pairs_opp)
print("    same wave    r = %s on n=%d" % (("%+.4f" % cs) if cs is not None else "n/a", ns))
print("    opposite     r = %s on n=%d" % (("%+.4f" % co) if co is not None else "n/a", no))
if cs is not None and co is not None:
    print("    gap %.4f -> the wave flip alone moves round-to-round correlation by that much"
          % (cs - co))
print()
print("VERDICT")
cands = [x for x in (implied36, c, cs) if x is not None]
if cands:
    lo, hi = min(cands), max(cands)
    print("    every estimate lands in [%+.3f, %+.3f]; the old default was 0.250." % (lo, hi))
    best = cs if cs is not None else (c if c is not None else implied36)
    print("    RHO should be the SAME-WAVE correlation (pure form, wave modelled separately):")
    print("    -> use RHO = %.3f" % max(0.0, best))
