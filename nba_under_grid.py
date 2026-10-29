"""NBA_UNDER_PREREG.md amendment 4: every %-below range for UNDER20's -150-or-better, non-threes flags (post-hoc; information)."""
import sys, numpy as np
sys.path.insert(0, ".")
exec(open("nba_tests4_checks.py").read().split("def run(")[0])   # builds `data`
rng = np.random.default_rng(7)
ok = lambda d: d["under"] >= 1 / 0.6 - 1e-9 and d["mk"] != "threes"
U = {s: [(1 - d["x"][2], d["under"] - 1 if not d["y"] else -1.0) for d in data[s] if ok(d)] for s in data}   # (% below, unit)
nights = {s: len({d["date"] for d in data[s]}) for s in data}
def band(s, lo, hi):
    v = np.array([u for b, u in U[s] if lo <= b < hi])
    if len(v) < 30:
        return None
    bs = np.sort([rng.choice(v, len(v)).mean() for _ in range(1000)])
    return len(v), v.mean(), bs[50], bs[950]
print("narrow bands (% below the line), -150 or better, no threes")
for lo, hi in ((0.20, 0.25), (0.25, 0.30), (0.30, 0.35), (0.35, 0.40), (0.40, 0.45), (0.45, 0.50), (0.50, 0.60), (0.60, 0.70), (0.70, 1.01)):
    row = []
    for s in ("2023-24", "2024-25"):
        b = band(s, lo, hi)
        row.append(f"n {b[0]:4d} ROI {b[1]:+.3f} [{b[2]:+.3f},{b[3]:+.3f}]" if b else "n < 30")
    print(f"  {int(lo*100):3d}-{int(min(hi,1)*100):3d}%: " + "  |  ".join(row))
print("\nall ranges lo-hi (both seasons), ranked by the worse season's ROI, n >= 150 each")
res = []
los = (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50)
his = (0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70, 1.01)
for lo in los:
    for hi in his:
        if hi <= lo + 0.04:
            continue
        b1, b2 = band("2023-24", lo, hi), band("2024-25", lo, hi)
        if b1 and b2 and b1[0] >= 150 and b2[0] >= 150:
            res.append((min(b1[1], b2[1]), lo, hi, b1, b2))
for worst, lo, hi, b1, b2 in sorted(res, reverse=True)[:14]:
    lab = f"{int(lo*100)}-{'max' if hi > 1 else int(hi*100)}%"
    print(f"  {lab:9s} 2023-24 n {b1[0]:4d} ({b1[0]/nights['2023-24']:.1f}/night) ROI {b1[1]:+.3f} | 2024-25 n {b2[0]:4d} ({b2[0]/nights['2024-25']:.1f}/night) ROI {b2[1]:+.3f} [{b2[2]:+.3f},{b2[3]:+.3f}]")
print(f"\n  ({len(res)} ranges tried)")
