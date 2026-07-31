import io
p="wnba_freeze.py"; s=io.open(p).read()
s=s.replace('VERSION = "v1.1"','VERSION = "v1.2"')
a=s.index('DECISION = ('); b=s.index('\n\n\ndef main()')
s=s[:a]+'''DECISION = (
    "v1.2 (2026-07-31) — the sticky-incumbent swap test is now BAND-AWARE. It compared raw EV while "
    "the ranking uses (odds, band, EV), so an incumbent could hold a slot while ranking WORSE on "
    "the canonical key, and hold it on the one metric this ledger shows is ANTI-predictive. Live "
    "case: DiLeo (band 0, odds 1.9091, EV 0.213) could not displace Carleton (band 1, odds 1.9804, "
    "EV 0.462), so the card kept a TIER B play over a TIER A one — and Carleton only held the slot "
    "because she was carded at 04:08, before the v1.1 correlation-cap fix. Stickiness was "
    "protecting the output of the bug v1.1 corrected. "
    "A challenger now displaces when it is better ON THE BAND (structural, and band membership "
    "barely moves during a slate, so it cannot churn); within the same band the original "
    "SWAP_MARGIN EV rule is unchanged, preserving the anti-churn property that stickiness exists "
    "for (57% of pools once carded more than the two plays a card holds). "
    "Tier records behind the ordering: A 14-3 / 82.4% / +0.73u per bet vs B 17-11 / 60.7% / "
    "+0.20u. RESTATEMENT COST: the counted record moves 33-15 / +19.05u to 33-16 / +18.05u — one "
    "additional graded loss enters as a different incumbent yields. Reported, not hidden.")'''+s[b:]
io.open(p,"w").write(s); print("  wnba_freeze bumped to v1.2")
