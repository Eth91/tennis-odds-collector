"""Does pga_sim simulate TOURNAMENTS, or only rank players?

Every number measured so far is a RANK statistic (win / top-N / make-cut). Ranks are invariant to
the level and almost invariant to the shared per-round shock, so they can be well calibrated while
the simulated tournament looks nothing like a real one. This scores the ABSOLUTE shape, using the
two tournament-level quantities the result object exposes:

  * the 36-hole CUT LINE  -- a joint statistic: it depends on where the whole field lands, not on
    any one player, so it is exactly what a marginal model cannot produce.
  * the FIELD's per-round scoring SPREAD -- how wide a day's scoring actually is.

METRIC = INTERVAL COVERAGE, which needs only the percentiles the sim exposes. The realised value
should fall inside the simulated p10-p90 band 80% of the time. Much less => the sim is TOO NARROW
(it thinks it knows more than it does); much more => too wide. Also reported: the standardised
residual z = (actual - mean)/sd, whose sd should be ~1.00, and whose mean should be ~0 (level bias).

TAU IS THE POINT. tau*w[r] is a shared per-round conditions shock and it cancels out of ranks
almost exactly -- measured, tau 0->4 moves the largest win probability by 0.27pp, under the 0.72pp
seed-to-seed noise. So NO rank market can identify it, and the earlier validation could not either.
It does NOT cancel out of these two statistics. If TAU is identifiable at all, it is identifiable
here, so every statistic is scored across a sweep.

Cut lines use the per-event rule from RU.cut_rule (fixed 2026-08-13); no-cut events contribute
only the spread statistic.
"""
import datetime as dt
import sqlite3
import sys
from collections import defaultdict

import numpy as np

import pga_ruler as RU
import pga_sim as PS
import pga_sim_validate as V

SIMS = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
TAUS = [0.0, 1.0, 2.0, 3.0]
SEED = 11

events = V.load_events()
all_rows = RU.all_rows()
first = min(e["date"] for e in events)
burn = (dt.date.fromisoformat(str(first)[:10]) + dt.timedelta(days=270)).isoformat()
usable = [e for e in events if e["date"] >= burn and e["struct"] in ("cut_R2", "no_cut")]
print("scoring %d events, %s .. %s, %d sims, spread=1.30\n"
      % (len(usable), usable[0]["date"], usable[-1]["date"], SIMS))

con = sqlite3.connect(f"file:{RU.DB}?mode=ro", uri=True, timeout=60)
rec = defaultdict(lambda: defaultdict(list))       # stat -> tau -> [(actual, mean, sd, p10, p90)]
skip = defaultdict(int)

for i, ev in enumerate(usable, 1):
    d0, eid = ev["date"], ev["eid"]
    byp = defaultdict(dict)
    for p, r, s in con.execute("SELECT player, rnd, score FROM rounds WHERE event_id=?", (eid,)):
        byp[p][int(r)] = float(s)
    r1 = {p: v[1] for p, v in byp.items() if 1 in v}
    if len(r1) < 40:
        skip["thin field"] += 1
        continue
    fm1 = sum(r1.values()) / len(r1)
    act = {"r1_spread": float(np.std(list(r1.values()), ddof=1))}
    if ev["struct"] == "cut_R2":
        adv = {p: v[1] + v[2] for p, v in byp.items() if 3 in v and 1 in v and 2 in v}
        fm2 = (sum(v[2] for v in byp.values() if 2 in v)
               / max(1, sum(1 for v in byp.values() if 2 in v)))
        if adv:
            act["cut_line"] = max(adv.values()) - (fm1 + fm2)     # field-relative

    train = V._train_rows(all_rows, d0)
    V.assert_no_leak(train, eid, d0)
    R, _g = PS.ratings_asof(d0, rows=train)
    field = [p for p in r1 if PS.lookup(R, p) is not None]
    if len(field) < max(30, 0.5 * len(r1)):
        skip["thin ratings"] += 1
        continue
    cut_n = RU.cut_rule(ev["name"], d0, n_field=len(r1))

    for tau in TAUS:
        res = PS.simulate(field, n=SIMS, seed=SEED, ratings=R, tau=tau,
                          cut_n=cut_n, spread=1.30)
        fr = res.field_round_dist().get(1) or {}
        if fr.get("sd"):
            # the sim's own round-1 spread, compared with the field's realised spread
            rec["r1_spread"][tau].append((act["r1_spread"], fr["sd"], None, None, None))
        if "cut_line" in act:
            cl = res.cut_line() or {}
            if cl.get("sd"):
                rec["cut_line"][tau].append((act["cut_line"], cl["mean"], cl["sd"],
                                             cl.get("p10"), cl.get("p90")))
    if i % 40 == 0:
        print("   ... %d/%d" % (i, len(usable)))

con.close()

print("\n" + "=" * 84)
print("CUT LINE — a JOINT statistic, the thing a marginal model cannot produce")
print("=" * 84)
print("   %-5s %5s %9s %9s %9s %9s   %s"
      % ("tau", "n", "bias", "sd(z)", "cover80", "sim sd", "reading"))
for tau in TAUS:
    v = [x for x in rec["cut_line"][tau] if x[2]]
    if not v:
        continue
    a = np.array([x[0] for x in v]); m = np.array([x[1] for x in v])
    s = np.array([x[2] for x in v])
    z = (a - m) / s
    cov = np.mean([(x[3] is not None and x[3] <= x[0] <= x[4]) for x in v])
    read = ("TOO NARROW" if np.std(z) > 1.35 else "too wide" if np.std(z) < 0.75 else "ok")
    if abs(np.mean(z)) > 0.5:
        read += " + BIASED"
    print("   %-5.1f %5d %9.2f %9.2f %9.3f %9.2f   %s"
          % (tau, len(v), np.mean(a - m), np.std(z), cov, np.mean(s), read))
print("   (cover80 should be 0.80; sd(z) should be 1.00; bias is strokes)")

print("\n" + "=" * 84)
print("FIELD ROUND-1 SCORING SPREAD — does a simulated day look as wide as a real one?")
print("=" * 84)
print("   %-5s %5s %10s %10s %10s   %s" % ("tau", "n", "actual sd", "sim sd", "ratio", "reading"))
for tau in TAUS:
    v = rec["r1_spread"][tau]
    if not v:
        continue
    a = np.array([x[0] for x in v]); m = np.array([x[1] for x in v])
    ratio = float(np.mean(m) / np.mean(a))
    read = ("sim too TIGHT" if ratio < 0.92 else "sim too WIDE" if ratio > 1.08 else "ok")
    print("   %-5.1f %5d %10.3f %10.3f %10.3f   %s"
          % (tau, len(v), np.mean(a), np.mean(m), ratio, read))

for k, n in skip.items():
    print("skipped %-18s %d" % (k, n))
