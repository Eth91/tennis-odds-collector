"""NBA_UNDER_PREREG.md amendment 5: the same %-from-the-line ranges for overs (post-hoc; information)."""
import sys, numpy as np
sys.path.insert(0, ".")
exec(open("nba_tests4_checks.py").read().split("def run(")[0])   # builds `data`
rng = np.random.default_rng(7)
nights = {s: len({d["date"] for d in data[s]}) for s in data}
def band(s, lo, hi, filt):
    v = np.array([d["over"] - 1 if d["y"] else -1.0 for d in data[s] if lo <= d["x"][2] - 1 < hi and filt(d)])
    if len(v) < 30:
        return None
    bs = np.sort([rng.choice(v, len(v)).mean() for _ in range(1000)])
    return len(v), v.mean(), bs[50], bs[950]
for fname, filt in (("overs -150 or better, no threes", lambda d: d["over"] >= 1 / 0.6 - 1e-9 and d["mk"] != "threes"),
                    ("all overs", lambda d: True)):
    print(f"\n== {fname}: projection X% ABOVE the line")
    for lo, hi in ((0.0, 0.10), (0.10, 0.20), (0.20, 0.25), (0.25, 0.30), (0.30, 0.35), (0.35, 0.40), (0.40, 0.50), (0.50, 0.75), (0.75, 9)):
        row = []
        for s in ("2023-24", "2024-25"):
            b = band(s, lo, hi, filt)
            row.append(f"n {b[0]:5d} ROI {b[1]:+.3f} [{b[2]:+.3f},{b[3]:+.3f}]" if b else "n < 30")
        print(f"  {int(lo*100):3d}-{'max' if hi > 5 else int(hi*100)}%: " + "  |  ".join(row))
    res = []
    for lo in (0.10, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50):
        for hi in (0.30, 0.35, 0.40, 0.50, 0.60, 0.75, 1.0, 9):
            if hi <= lo + 0.04:
                continue
            b1, b2 = band("2023-24", lo, hi, filt), band("2024-25", lo, hi, filt)
            if b1 and b2 and b1[0] >= 150 and b2[0] >= 150:
                res.append((min(b1[1], b2[1]), lo, hi, b1, b2))
    print(f"  best ranges by the worse season ({len(res)} tried, n >= 150 each):")
    for worst, lo, hi, b1, b2 in sorted(res, reverse=True)[:6]:
        print(f"    {int(lo*100)}-{'max' if hi > 5 else int(hi*100)}%  2023-24 n {b1[0]:5d} ROI {b1[1]:+.3f} | 2024-25 n {b2[0]:5d} ROI {b2[1]:+.3f} [{b2[2]:+.3f},{b2[3]:+.3f}]")
