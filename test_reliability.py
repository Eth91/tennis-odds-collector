"""Is the birdie model's player spread REAL, or noise? Settled against outcomes, not the market.

The dispersion test showed our P(over) spread is 1.81x the market's with r=0.664 — we separate
players far more than the market while reproducing under half its variance. Either we know
something it doesn't, or we are over-dispersed and our tail flags are artifacts. The market's
opinion cannot settle that; realized birdie counts can.

Leak-free design, no as-of machinery needed: split each player's harvested rounds in half BY
DATE, fit their per-par rates on the EARLY half, then predict each LATE-half round using that
round's OWN hole mix (we store p3h/p4h/p5h per round, so the par mix is exact, not assumed).
Bucket by predicted probability and compare with what actually happened.

The diagnostic is the reliability SLOPE of realized on predicted. Slope 1 = the spread is real.
Slope well under 1 = we are over-dispersed and should shrink player deviations by that factor.
"""
import sqlite3
import statistics as st
from collections import defaultdict

import pga_birdies as B
import pga_ruler as RU

K_TARGET = 4                      # P(>= 4 birdies), near the typical posted line
con = sqlite3.connect(B.DB)
# no date subquery: it was a correlated LIKE over 42k rows (O(n*m)) and the value was never
# used — tid embeds the season (R2024/R2025/R2026) so sorting on (tid, rnd) is chronological.
rows = con.execute(
    "SELECT player, tid, rnd, p3h, p3b, p4h, p4b, p5h, p5b FROM birdie_rounds").fetchall()
con.close()

by_pl = defaultdict(list)
for pl, tid, rnd, a3, b3, a4, b4, a5, b5 in rows:
    by_pl[RU.norm(pl)].append((str(tid), rnd, a3 or 0, b3 or 0, a4 or 0, b4 or 0, a5 or 0, b5 or 0))

# global per-par field rates, for shrinkage
tot = defaultdict(lambda: [0, 0])
for v in by_pl.values():
    for _t, _r, a3, b3, a4, b4, a5, b5 in v:
        tot[3][0] += a3; tot[3][1] += b3
        tot[4][0] += a4; tot[4][1] += b4
        tot[5][0] += a5; tot[5][1] += b5
g = {p: (v[1] / v[0] if v[0] else .15) for p, v in tot.items()}
print("field rates: par3 %.3f par4 %.3f par5 %.3f" % (g[3], g[4], g[5]))

preds, obs = [], []
for pl, v in by_pl.items():
    if len(v) < 10:
        continue
    v.sort(key=lambda z: (z[0], z[1]))          # tid then round == chronological enough
    h = len(v) // 2
    early, late = v[:h], v[h:]
    agg = {3: [0, 0], 4: [0, 0], 5: [0, 0]}
    for _t, _r, a3, b3, a4, b4, a5, b5 in early:
        agg[3][0] += a3; agg[3][1] += b3
        agg[4][0] += a4; agg[4][1] += b4
        agg[5][0] += a5; agg[5][1] += b5
    rate = {}
    for par in (3, 4, 5):
        hh, bb = agg[par]
        kh = B.K_H_PAR.get(par, B.K_H)
        rate[par] = min((bb + kh * g[par]) / (hh + kh), 0.95)
    for _t, _r, a3, b3, a4, b4, a5, b5 in late:
        mixr = {3: a3, 4: a4, 5: a5}
        if sum(mixr.values()) < 15:
            continue
        p = B.p_x_or_more(rate, K_TARGET, mixr)
        preds.append(p)
        obs.append(1.0 if (b3 + b4 + b5) >= K_TARGET else 0.0)

print("out-of-sample player-rounds: %d" % len(preds))
if len(preds) < 500:
    raise SystemExit("too few")
print("mean predicted %.4f vs realized %.4f  (level gap %+.2f pts)"
      % (st.mean(preds), st.mean(obs), 100 * (st.mean(preds) - st.mean(obs))))
print()
print("RELIABILITY by predicted-probability decile")
print("  %-16s %6s %10s %10s" % ("bucket", "n", "predicted", "realized"))
srt = sorted(zip(preds, obs))
nb = 10
sz = len(srt) // nb
xs, ys = [], []
for i in range(nb):
    chunk = srt[i * sz:(i + 1) * sz] if i < nb - 1 else srt[i * sz:]
    if not chunk:
        continue
    px = st.mean(c[0] for c in chunk)
    py = st.mean(c[1] for c in chunk)
    xs.append(px); ys.append(py)
    print("  %-16s %6d %9.3f %10.3f" % ("d%d" % (i + 1), len(chunk), px, py))
mx, my = st.mean(xs), st.mean(ys)
den = sum((x - mx) ** 2 for x in xs)
slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else 0
print()
print("  reliability slope (realized on predicted) = %+.3f" % slope)
if slope < 0.8:
    print("  OVER-DISPERSED against OUTCOMES: our player spread is wider than reality by")
    print("  ~1/%.2f = %.2fx. Extreme predictions do not come true at their stated rate, so the" % (slope, 1/slope))
    print("  tail flags — which is where every birdie edge sits — are largely spread artefacts.")
    print("  The market's tighter spread (sd ratio 1.81x) was the more honest one.")
elif slope > 1.2:
    print("  UNDER-DISPERSED: reality separates players MORE than we do.")
else:
    print("  CALIBRATED: the spread is real, so the wider-than-market dispersion is knowledge,")
    print("  not noise — the market is the under-dispersed one.")
