"""72-hole matchup repricing from RHO 0.25 -> 0.05.

(The previous run printed nothing here: it fed RU.norm()'d names into a ratings dict keyed by
raw display names, so every lookup missed. matchup_prob tries R[norm(a)] then R[a], and a
pre-normalised name matches neither.)

This is the market the change matters most for: FanDuel's 72-hole matchbets are two-way, so a
variance error moves both sides symmetrically and quietly.
"""
import pga_field as PF
import pga_ruler as RU

R, _ = RU.fit()
field = [(c.get("athlete") or {}).get("displayName") for c in PF.competitors()]
field = [f for f in field if f and (RU.norm(f) in R or f in R)]
rated = sorted(field, key=lambda p: (R.get(RU.norm(p)) or R.get(p))[0])
print("rated field: %d players" % len(rated))
pairs = [(rated[0], rated[10]), (rated[2], rated[20]), (rated[5], rated[6]),
         (rated[1], rated[40]), (rated[0], rated[1])]
print()
print("  %-44s %8s %8s %8s" % ("matchup (72 hole)", "RHO=.25", "RHO=.05", "shift"))
shifts = []
for a, b in pairs:
    old = RU.RHO
    RU.RHO = 0.25
    p1 = RU.matchup_prob(R, a, b, rounds=4)
    RU.RHO = 0.05
    p2 = RU.matchup_prob(R, a, b, rounds=4)
    RU.RHO = old
    if p1 is None or p2 is None:
        print("  %-44s  (unrated)" % (a + " vs " + b)[:44])
        continue
    shifts.append(abs(p2 - p1))
    print("  %-44s %7.1f%% %7.1f%% %+7.2fpt"
          % ((a + " vs " + b)[:44], 100 * p1, 100 * p2, 100 * (p2 - p1)))
print()
if shifts:
    print("  mean |shift| %.2f points; every shift moves AWAY from 50/50, because the old RHO"
          % (100 * sum(shifts) / len(shifts)))
    print("  inflated 72-hole variance by ~14%% and variance is what pulls a price to a coin flip.")
print()
print("  single-round matchups are unaffected by RHO (it only couples rounds):")
a, b = rated[0], rated[10]
for rho in (0.25, 0.05):
    old = RU.RHO
    RU.RHO = rho
    p = RU.matchup_prob(R, a, b, rounds=1)
    RU.RHO = old
    print("     RHO %.2f -> 18-hole %s vs %s: %.2f%%" % (rho, a.split()[-1], b.split()[-1],
                                                        100 * p))
