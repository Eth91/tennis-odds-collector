"""The sticky-incumbent swap test used raw EV while the ranking uses (odds, band, EV).

CONSEQUENCE, live on 2026-07-31: DiLeo's key (1.9091, 0, -0.213) beats Carleton's (1.9804, 1,
-0.462) on BOTH leading terms — shorter odds and inside the validated 3-8 band. She should hold the
POR points slot. She cannot, because Carleton was carded at 04:08 (before the correlation-cap fix)
and an incumbent only yields when a challenger beats it by SWAP_MARGIN of EV. Carleton's EV is
0.462 against DiLeo's 0.213, so the swap can never fire.

So the stickiness rule was protecting the output of the very bug that was just fixed, and doing it
with EV — the one metric this ledger has repeatedly shown to be ANTI-predictive (EV>=.20 hits worse
than EV<.20; tier A 82.4% vs tier B 60.7%).

THE FIX, deliberately minimal. Stickiness exists for a real reason: with no hysteresis the card
re-ranked on every scan and 57% of team-game pools ended up carding more than the two plays a card
can hold (TOR cycled through seven). That must not come back. So:

    challenger in the A-BAND, incumbent not  -> displace (band is stable intraday and is the
                                               twice-validated signal; this is a structural
                                               improvement, not a wiggle)
    same band                                -> unchanged: EV must beat SWAP_MARGIN
    challenger out of band, incumbent in     -> hold

Band membership barely moves during a slate, so this cannot churn the way odds or EV would. It
fires only when a genuinely better-classified play appears — which is exactly the case that was
being blocked.
"""
import ast
import io
import shutil

P = "wnba_slip.py"
s = io.open(P, encoding="utf-8").read()

if "_band_of" in s:
    print("  = swap rule already band-aware")
    raise SystemExit(0)

old = """        incumbents = [g for g in slog.get((pd_, tm), []) if g in groups]
        ranked = sorted(groups, key=gkey)

        def _ev(g):
            return max((x.get("ev") or 0.0) for x in groups[g])"""
new = """        incumbents = [g for g in slog.get((pd_, tm), []) if g in groups]
        ranked = sorted(groups, key=gkey)

        def _ev(g):
            return max((x.get("ev") or 0.0) for x in groups[g])

        def _band_of(g):
            \"\"\"0 when the group sits in the validated 3-8 d_min band, else 1.

            The swap test below used EV alone while gkey ranks on (odds, band, EV), so an incumbent
            could hold a slot while ranking WORSE on the canonical key — and hold it on EV, which
            this ledger shows is anti-predictive (tier A 82.4% vs tier B 60.7%). 2026-07-31: DiLeo
            (band 0, odds 1.9091) could not displace Carleton (band 1, odds 1.9804) because
            Carleton's EV was higher, so the card kept the tier-B play over the tier-A one.\"\"\"
            dm = groups[g][0].get("d_min")
            return 0 if (dm is not None and 3 <= dm <= 8) else 1"""
assert old in s, "incumbent block anchor missing"
s = s.replace(old, new, 1)

old_swap = """            best = next((x for x in ranked
                         if x != g and not (_comps(x[1]) & used) and x not in picks), None)
            if best is not None and _ev(best) - _ev(g) >= SWAP_MARGIN:
                g, cs = best, _comps(best[1])             # genuinely better -> allowed to displace"""
new_swap = """            best = next((x for x in ranked
                         if x != g and not (_comps(x[1]) & used) and x not in picks), None)
            # A challenger displaces the incumbent when it is BETTER ON THE BAND (structural, and
            # band membership barely moves during a slate, so this cannot churn), or when the two
            # share a band and it beats EV by the margin (the original anti-churn rule, unchanged).
            # Using EV alone let a tier-B incumbent block a tier-A challenger indefinitely.
            if best is not None and (
                    _band_of(best) < _band_of(g)
                    or (_band_of(best) == _band_of(g) and _ev(best) - _ev(g) >= SWAP_MARGIN)):
                g, cs = best, _comps(best[1])             # genuinely better -> allowed to displace"""
assert old_swap in s, "swap anchor missing"
s = s.replace(old_swap, new_swap, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/wnba_slip.preswap.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + swap test is band-aware: a tier-A challenger can displace a tier-B incumbent")
