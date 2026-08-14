"""St Jude: what the slope change did, and where the tournament stands after R1.

Three columns:
  OLD   SHAPE_SLOPE=1.30 applied to every market  — what shipped until today
  NEW   the fitted non-major table                — what ships now
  LIVE  conditioned on the R1 scores actually posted

⚠️ THE SLOPE DOES NOT APPLY TO THE LIVE COLUMN. pga_ruler skips _recal_shape entirely once
`progress` is passed ("SHAPE_SLOPE was fitted on pre-tournament sims, and once posted scores
condition the distribution it is already sharp"). So the regime split changes PRE-TOURNAMENT
pricing only — worth knowing before anyone reads a live board and wonders why it looks unmoved.
"""
import sqlite3

import pga_ruler as RU

EV = "PGA FedEx St Jude Championship 2026"
ASOF = "2026-08-13"

R_raw, _ = RU.fit(asof=ASOF)
R = {RU.norm(k): v for k, v in R_raw.items()}
con = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
eid = con.execute("SELECT event_id FROM rounds WHERE event LIKE ? AND date LIKE ? LIMIT 1",
                  ("%St. Jude%", "2026%")).fetchone() or \
      con.execute("SELECT event_id FROM rounds WHERE event LIKE ? AND date LIKE ? LIMIT 1",
                  ("%St Jude%", "2026%")).fetchone()
eid = eid[0]
field = [r[0] for r in con.execute("SELECT DISTINCT player FROM rounds WHERE event_id=?", (eid,))]
r1 = {p: float(s) for p, s in con.execute(
    "SELECT player, score FROM rounds WHERE event_id=? AND rnd=1", (eid,))}
con.close()

cut_n = RU.cut_rule(EV, ASOF, n_field=len(field))
new_sl = RU.shape_slopes(EV)
print("field %d · cut %s · new shape = %s\n"
      % (len(field), "NO CUT" if cut_n is None else "top-%d" % cut_n,
         "non-major fitted table" if new_sl else "majors 1.30"))

old = RU.simulate(R, field, n_sims=20000, seed=13, cut_n=cut_n, shape_slope=1.30, reps=2)
new = RU.simulate(R, field, n_sims=20000, seed=13, cut_n=cut_n, shape_slope=new_sl, reps=2)
live = RU.simulate(R, field, n_sims=20000, seed=13, cut_n=cut_n, shape_slope=new_sl,
                   progress={p: [s] for p, s in r1.items()}) if r1 else {}

print("=" * 92)
print("PRE-TOURNAMENT — what the slope change did (ranked by NEW win%)")
print("=" * 92)
print("   %-22s %15s %15s %15s" % ("player", "win  old→new", "top10 old→new", "top20 old→new"))
for p in sorted(new, key=lambda x: -new[x]["win"])[:12]:
    print("   %-22s %6.2f→%-6.2f %6.2f→%-6.2f %6.2f→%-6.2f"
          % (p[:22], 100 * old[p]["win"], 100 * new[p]["win"],
             100 * old[p]["top10"], 100 * new[p]["top10"],
             100 * old[p]["top20"], 100 * new[p]["top20"]))
for lbl, k in (("win", "win"), ("top10", "top10"), ("top20", "top20")):
    print("   field total %-6s old %.2f  new %.2f"
          % (lbl, sum(v[k] for v in old.values()), sum(v[k] for v in new.values())))

if live:
    fm = sum(r1.values()) / len(r1)
    print("\n" + "=" * 92)
    print("LIVE after R1 (field mean %.2f, low 65) — slope NOT applied in-play, by design" % fm)
    print("=" * 92)
    print("   %-22s %6s %8s %8s %8s   %s"
          % ("player", "R1", "win", "top5", "top10", "pre-tourn win"))
    for p in sorted(live, key=lambda x: -live[x]["win"])[:12]:
        print("   %-22s %6s %7.2f%% %7.2f%% %7.2f%%   %6.2f%%"
              % (p[:22], ("%g" % r1[p]) if p in r1 else "-", 100 * live[p]["win"],
                 100 * live[p]["top5"], 100 * live[p]["top10"], 100 * new[p]["win"]))
    mv = sorted(live, key=lambda x: -(live[x]["win"] - new[x]["win"]))[:4]
    print("\n   biggest R1 movers:")
    for p in mv:
        print("     %-22s R1 %g   win %.2f%% -> %.2f%%  (%+.2f)"
              % (p[:22], r1.get(p, 0), 100 * new[p]["win"], 100 * live[p]["win"],
                 100 * (live[p]["win"] - new[p]["win"])))
