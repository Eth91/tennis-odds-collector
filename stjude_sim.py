"""What the simulator said for the FedEx St Jude Championship — tournament and R1.

Ratings are fit AS-OF 2026-08-13, so `fit` sees only rounds strictly BEFORE today: today's R1 is
not in the training set and this is a genuine pre-tournament forecast. R1 has since been played,
so the R1 half can be scored against what actually happened -- the only part of this week that is
gradeable yet.

Settings are the live ones as of today: cut_n=None (St Jude has NO CUT -- verified in the
warehouse, 70/70/70/70 in 2023-24 and 69/69/69/69 in 2025), and the non-major fitted shape table.
"""
import sqlite3
from collections import defaultdict

import pga_ruler as RU
import pga_sim as PS

EV = "PGA FedEx St Jude Championship 2026"
ASOF = "2026-08-13"

R_raw, _ = RU.fit(asof=ASOF)
R = {RU.norm(k): v for k, v in R_raw.items()}

con = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
eid = con.execute("SELECT event_id FROM rounds WHERE event LIKE ? AND date LIKE ? LIMIT 1",
                  ("%St. Jude%", "2026%")).fetchone()
if not eid:
    eid = con.execute("SELECT event_id FROM rounds WHERE event LIKE ? AND date LIKE ? LIMIT 1",
                      ("%St Jude%", "2026%")).fetchone()
eid = eid[0]
field = [r[0] for r in con.execute("SELECT DISTINCT player FROM rounds WHERE event_id=?", (eid,))]
r1 = {p: s for p, s in con.execute(
    "SELECT player, score FROM rounds WHERE event_id=? AND rnd=1", (eid,))}
con.close()

cut_n = RU.cut_rule(EV, ASOF, n_field=len(field))
shp = RU.shape_slopes(EV)
print("field %d · cut rule: %s · shape: %s"
      % (len(field), "NO CUT" if cut_n is None else "top-%d" % cut_n,
         "majors 1.30" if shp is None else "non-major fitted table"))
print("ratings as-of %s (today's R1 excluded from the fit)\n" % ASOF)

sim = RU.simulate(R, field, n_sims=20000, seed=13, cut_n=cut_n, shape_slope=shp, reps=2)

print("=" * 78)
print("72-HOLE TOURNAMENT FORECAST (pre-tournament)")
print("=" * 78)
print("   %-24s %7s %7s %7s %7s" % ("player", "win", "top5", "top10", "top20"))
for p in sorted(sim, key=lambda x: -sim[x]["win"])[:12]:
    v = sim[p]
    print("   %-24s %6.2f%% %6.2f%% %6.2f%% %6.2f%%"
          % (p[:24], 100 * v["win"], 100 * v["top5"], 100 * v["top10"], 100 * v["top20"]))
print("   %-24s %6.2f%% %6.2f%% %6.2f%% %6.2f%%"
      % ("— field total —", 100 * sum(v["win"] for v in sim.values()),
         100 * sum(v["top5"] for v in sim.values()), 100 * sum(v["top10"] for v in sim.values()),
         100 * sum(v["top20"] for v in sim.values())))

# ── R1: leader probabilities from pga_sim, which exposes per-round leadership ────────────────
Rp, _g = PS.ratings_asof(ASOF)
fp = [p for p in field if PS.lookup(Rp, p) is not None]
res = PS.simulate(fp, n=20000, seed=13, ratings=Rp, cut_n=None, spread=1.30)
lead = res.leader(1, ties=True)

print("\n" + "=" * 78)
print("ROUND 1 FORECAST vs WHAT ACTUALLY HAPPENED")
print("=" * 78)
if r1:
    fm = sum(r1.values()) / len(r1)
    best = min(r1.values())
    winners = sorted([p for p, s in r1.items() if s == best])
    print("   actual R1: %d players, field mean %.2f, low round %g by %s"
          % (len(r1), fm, best, ", ".join(w[:22] for w in winners[:4])))
    rd = res.round_dist(fp[0]) if fp else None
    fr = res.field_round_dist().get(1) or {}
    print("   sim R1 field: mean %.2f  sd %.2f  (actual sd %.2f)"
          % (fr.get("mean", float("nan")), fr.get("sd", float("nan")),
             (sum((s - fm) ** 2 for s in r1.values()) / (len(r1) - 1)) ** 0.5))
print("\n   %-24s %10s   %s" % ("player", "P(R1 lead)", "actual R1"))
for p in sorted(lead, key=lambda x: -lead[x])[:12]:
    print("   %-24s %9.2f%%   %s" % (p[:24], 100 * lead[p],
                                     ("%g" % r1[p]) if p in r1 else "-"))

if r1:
    print("\n   where the ACTUAL R1 leaders were ranked by the sim:")
    order = sorted(lead, key=lambda x: -lead[x])
    for w in winners[:5]:
        rk = order.index(w) + 1 if w in order else None
        print("     %-24s shot %g · sim rank %s of %d · P(lead) %.2f%%"
              % (w[:24], r1[w], rk if rk else "unrated", len(order),
                 100 * lead.get(w, 0.0)))
