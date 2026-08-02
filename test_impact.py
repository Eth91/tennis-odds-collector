"""What the measured constants actually change, in prices and in holdout accuracy.

Two separate questions:
  (1) did the RATING path get better or worse? Only K_SHRINK (12->11) touches it, so the 2026
      holdout walk-forward should be essentially unchanged — a big move either way would mean
      something unintended leaked into fit().
  (2) how much do RHO and K_FIT move the PRICES? They never touch fit(), so walk-forward
      cannot see them; their effect shows up in matchup probabilities and tournament
      outcomes, which is where money is actually placed.
"""
import statistics as st

import pga_field as PF
import pga_ruler as RU

print("[1] RATING PATH — 2026 holdout walk-forward")
rows = RU.all_rows()
for ks in (12.0, 11.0):
    acc, rmse, n = RU.walk_forward(seasons=(2026,), verbose=False, rows=rows, k_shrink=ks)
    print("    K_SHRINK %.0f: accuracy %.4f  RMSE %.4f  (n=%d)%s"
          % (ks, acc, rmse, n, "   <- measured" if ks == 11.0 else "   <- old"))

print()
print("[2] PRICE IMPACT of RHO 0.25 -> 0.05 (72-hole matchups)")
R, _ = RU.fit()
field = [(c.get("athlete") or {}).get("displayName") for c in PF.competitors()]
field = [f for f in field if f and (RU.norm(f) in R or f in R)]
rated = sorted(((RU.norm(p), (R.get(RU.norm(p)) or R[p])[0]) for p in field),
               key=lambda kv: kv[1])
pairs = [(rated[0][0], rated[10][0]), (rated[2][0], rated[20][0]),
         (rated[5][0], rated[6][0]), (rated[1][0], rated[40][0])]
print("    %-46s %8s %8s %7s" % ("matchup (72 hole)", "RHO=.25", "RHO=.05", "shift"))
for a, b in pairs:
    old_rho = RU.RHO
    RU.RHO = 0.25
    p1 = RU.matchup_prob(R, a, b, rounds=4)
    RU.RHO = 0.05
    p2 = RU.matchup_prob(R, a, b, rounds=4)
    RU.RHO = old_rho
    if p1 is None or p2 is None:
        continue
    print("    %-46s %7.1f%% %7.1f%% %+6.1fpt"
          % ((a + " vs " + b)[:46], 100 * p1, 100 * p2, 100 * (p2 - p1)))

print()
print("[3] PRICE IMPACT on TOURNAMENT outcomes (top-5 / win for the favourites)")
for rho in (0.25, 0.05):
    old_rho = RU.RHO
    RU.RHO = rho
    sim = RU.simulate(R, field, n_sims=6000, seed=4)
    RU.RHO = old_rho
    if not sim:
        print("    RHO %.2f: field too small" % rho)
        continue
    top = sorted(sim.items(), key=lambda kv: -kv[1]["win"])[:5]
    tot_top5_of_fav5 = sum(v["top5"] for _p, v in top)
    print("    RHO %.2f: best win %.1f%% | top-5 favourites hold %.2f of the 5 top-5 slots "
          "| cut sd %.3f"
          % (rho, 100 * top[0][1]["win"], tot_top5_of_fav5,
             st.pstdev([v["cut"] for v in sim.values()])))
    print("             " + ", ".join("%s %.1f%%" % (p.split()[-1], 100 * v["win"])
                                      for p, v in top))

print()
print("[4] PRICE IMPACT of K_FIT 8 -> 105 (course-fit adjustment magnitude)")
import pga_context as C
evn = PF.event().get("name") or ""
mags = []
for p in field[:150]:
    d, n = C.course_fit(p, evn)
    if n >= 2:
        mags.append(abs(d))
if mags:
    print("    |course-fit| now: mean %.3f str, max %.3f str over %d players"
          % (st.mean(mags), max(mags), len(mags)))
    print("    at K_FIT=8 the same raw deviations would be %.1fx larger"
          % ((4 + 105.0) / (4 + 8.0)))
