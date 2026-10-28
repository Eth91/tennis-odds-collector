"""NBA_UNDER_PREREG.md amendment 2: UNDER20's cut swept from 20% to 40% below the line (post-hoc; information)."""
import sys, numpy as np
sys.path.insert(0, ".")
exec(open("nba_tests4_checks.py").read().split("def run(")[0])   # builds `data`
rng = np.random.default_rng(7)
def ci(v):
    bs = np.sort([rng.choice(v, len(v)).mean() for _ in range(2000)])
    return bs[100], bs[1900]
for filt, name in ((lambda d: True, "all flags"), (lambda d: d["under"] >= 1 / 0.6 - 1e-9 and d["mk"] != "threes", "-150 or better, no threes")):
    print(f"\n== {name}")
    for s in ("2023-24", "2024-25"):
        nights = len({d["date"] for d in data[s]})
        for lo, hi, lab in ((0.0, 0.80, "20%+ below"), (0.0, 0.75, "25%+ below"), (0.0, 0.70, "30%+ below"), (0.0, 0.65, "35%+ below"), (0.0, 0.60, "40%+ below"),
                            (0.75, 0.80, "  only 20-25%"), (0.70, 0.75, "  only 25-30%"), (0.60, 0.70, "  only 30-40%")):
            v = np.array([d["under"] - 1 if not d["y"] else -1.0 for d in data[s] if lo <= d["x"][2] < hi and filt(d)])
            if len(v):
                a, b = ci(v)
                hit = np.mean([not d["y"] for d in data[s] if lo <= d["x"][2] < hi and filt(d)])
                print(f"  {s} {lab:16s} n {len(v):5d} ({len(v)/nights:4.1f}/night)  hit {hit:.3f}  ROI {v.mean():+.4f}  90% [{a:+.3f}, {b:+.3f}]")
