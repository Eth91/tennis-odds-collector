"""RESOLVE THE CONTRADICTION before registering anything.

PR-005 says ladder rungs LOSE (3-9, -45.9%). The min-gap-suppressed rungs WON (11-6, +29.9%).
Both are 'extra rungs on the same player-stat', so they cannot both be true as stated.

Hypothesis that would unify them: value decays with DISTANCE FROM THE BASE LINE. Rungs a step
away are fine; rungs far up the ladder are not. Test distance directly, on ALL rungs -- taken,
min-gap-suppressed, and alt alike."""
import sqlite3, sys, statistics as st, math
from collections import defaultdict
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_slip as S
c = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/wnba_ledger.sqlite?mode=ro", uri=True, timeout=30)
c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute("SELECT * FROM predictions")]
overs = [r for r in rows if (r.get("side") or "over")=="over" and (r.get("tier") or "firm")!="n1"]
kept, dropped = S.current_selection(overs, commit=False)
def why(d):
    if isinstance(d, tuple) and len(d)==2: return d[0], str(d[1])
    return d, str((d or {}).get("_suppressed") or "dropped")
mingap = [r for r, w in map(why, dropped) if "min-gap" in w]
print(f"tracked {len(kept)} | min-gap suppressed {len(mingap)}")
def b(r):
    res=str(r.get("result") or "").lower()
    return "VOID" if res=="void" else ("W" if res=="over" else ("L" if res=="under" else "P"))
# universe = taken + min-gap-suppressed (both are rungs the model wanted)
uni = kept + mingap
grp = defaultdict(list)
for r in uni: grp[(r["pred_date"], r["player"], r["stat"])].append(r)
for k, v in grp.items():
    base = min(v, key=lambda r: abs(float(r["odds"]) - 2.0))
    for r in v:
        r["_dist"] = round(abs(float(r["line"]) - float(base["line"])), 1)
        r["_isbase"] = (id(r) == id(base))
def rec(sel, lab):
    W=[r for r in sel if b(r)=="W"]; L=[r for r in sel if b(r)=="L"]
    n=len(W)+len(L)
    if n < 5: print(f"  {lab:36s} thin (n={n})"); return
    u=sum(float(r["odds"])-1 for r in W)-len(L)
    ao=st.mean([float(r["odds"]) for r in W+L])
    print(f"  {lab:36s} {len(W):2d}-{len(L):<2d} {len(W)/n*100:5.1f}%  {u:+7.2f}u  ROI {u/n*100:+6.1f}%  avg odds {ao:.2f}")
FWD = lambda r: str(r["pred_date"]) >= "2026-07-31"
print("\n=== ALL-TIME: performance by DISTANCE from the base rung ===")
for d in sorted({r["_dist"] for r in uni}):
    rec([r for r in uni if r["_dist"] == d], f"distance {d:+.1f} from base")
print("\n=== FORWARD only ===")
for d in sorted({r["_dist"] for r in uni if FWD(r)}):
    rec([r for r in uni if FWD(r) and r["_dist"] == d], f"distance {d:+.1f} from base")
print("\n=== the two conflicting groups, side by side (all-time) ===")
rec([r for r in kept if r["_isbase"]], "BASE rungs (taken)")
rec(mingap, "MIN-GAP suppressed (extra, near base)")
rec([r for r in kept if not r["_isbase"]], "TAKEN non-base rungs (the alts)")
print("\n  distance profile of each group:")
for lab, sel in (("min-gap suppressed", mingap), ("taken non-base", [r for r in kept if not r["_isbase"]])):
    ds = [r["_dist"] for r in sel]
    if ds: print(f"    {lab:22s} median distance {st.median(ds):.1f}  mean {st.mean(ds):.1f}  max {max(ds):.1f}")
