"""Is the TOR cascade trimmed by SAMPLE rather than dropped by a fault?
wnba_alert.py:368 -- `if w["n_without"] < 2 and len(outs) > 1` -- shrinks the cascade when the
beneficiary has too few games without the WHOLE set. With 6 outs that sample is usually 0."""
import sys, itertools
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_wowy as W
pl = W.players()
def dates(n):
    p = pl.get(n)
    lg = W.game_log(p["id"]) or [] if p else []
    return {str(g.get("date"))[:10] for g in lg if (g.get("min") or 0) > 0}
BEN = "Isabelle Harrison"
ben = dates(BEN)
ALL6 = ["Marina Mabrey", "Aneesah Morrow", "Brittney Sykes", "Julie Allemand", "Maria Conde", "Nyara Sabally"]
USED = ["Marina Mabrey", "Aneesah Morrow", "Brittney Sykes"]
d = {n: dates(n) for n in ALL6}
print(f"{BEN} played {len(ben)} games\n")
print("games WITHOUT each single out:")
for n in ALL6:
    print(f"   without {n:20s} {len(ben - d[n]):3d}")
def without(names):
    s = set(ben)
    for n in names: s -= d[n]
    return len(s)
print(f"\nwithout ALL SIX outs           : {without(ALL6):3d}   <- gate needs >= 2")
print(f"without the THREE actually used: {without(USED):3d}")
print("\nlargest subsets that still clear n_without >= 2:")
best = []
for k in range(len(ALL6), 0, -1):
    ok = [c for c in itertools.combinations(ALL6, k) if without(c) >= 2]
    if ok:
        best = ok
        print(f"   size {k}: {len(ok)} subset(s) qualify, e.g. {list(ok[0])}  (n_without={without(ok[0])})")
        break
print(f"\n   -> the cascade the model used has size {len(USED)}; the largest qualifying size is "
      f"{len(best[0]) if best else 0}")
