"""HALF_LIFE_D 120 -> 270 days. The only TUNED constant, and it generalised.

Tuned on 2024-25 events with 2026 held out. The tune-set curve is a clean interior peak, not a
ramp — which is what a real optimum looks like:
    45d 0.5721 | 60d 0.5779 | 90d 0.5809 | 120d 0.5833 | 180d 0.5847
    270d 0.5862  <- best | 365d 0.5849 | no decay 0.5811
"No decay" scoring WORSE than 120 matters: recency is real, it just operates over roughly nine
months rather than four. And 120 was on the wrong side of the peak.

HELD-OUT CONFIRMATION on 2026, which was never used to choose it:
    120d accuracy 0.5885  ->  270d 0.5967   (+0.0082)
Against the measured ordering ceiling of 0.604, that lifts us from 85% to 93% of all
obtainable signal — the largest single gain in this calibration pass.

RMSE prefers ~90-120 days and worsens slightly here (2.8203 -> 2.8206 on holdout, a rounding
difference). That trade is taken deliberately: matchups and top-N markets are priced off
ORDERING, and the ordering gain is 15x larger than the RMSE cost.
"""
import ast, io
p = "pga_ruler.py"
s = io.open(p, encoding="utf-8").read()
old = "HALF_LIFE_D = 120.0     # recency half-life for the rating (form vs ability balance)"
new = """HALF_LIFE_D = 270.0     # TUNED 2026-07-29 on 2024-25 with 2026 HELD OUT — the only tuned
                        # constant here. Tune-set curve is a clean interior peak:
                        #   45d .5721  60d .5779  90d .5809  120d .5833  180d .5847
                        #   270d .5862 <-best  365d .5849  no-decay .5811
                        # 'No decay' scoring worse than 120 shows recency IS real; it just
                        # acts over ~9 months, and 120 sat on the wrong side of the peak.
                        # HELD-OUT 2026: .5885 -> .5967 (+.0082), i.e. 85% -> 93% of the
                        # measured 0.604 ordering ceiling. RMSE prefers ~90-120 and gives up
                        # 0.0003 here; taken deliberately, since matchups and top-N are
                        # priced off ordering and the ordering gain is ~15x the RMSE cost."""
if "TUNED 2026-07-29" in s:
    print("  = already 270")
else:
    assert old in s
    s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + HALF_LIFE_D 120 -> 270 (tuned, holdout-confirmed)")
