"""Rank the displaced plays WITHIN their team-game so a specific increment can be registered.
Pooling "everything the TOP-2 cap dropped" mixes the 3rd-best play with the 6th and would let me
pick the flattering slice after the fact -- the PR-002 mistake."""
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
dl = [why(d) for d in dropped]
top2 = [r for r, w in dl if "top-2" in w]
mingap = [r for r, w in dl if "min-gap" in w]
def b(r):
    res=str(r.get("result") or "").lower()
    return "VOID" if res=="void" else ("W" if res=="over" else ("L" if res=="under" else "P"))
# base-rung lens (orthogonal to PR-005): one rung per player-stat, nearest even
def basefilter(pool):
    g = defaultdict(list)
    for r in pool: g[(r["pred_date"], r["player"], r["stat"])].append(r)
    return [min(v, key=lambda r: (abs(float(r["odds"])-2.0), float(r["line"]))) for v in g.values()]
# rank displaced plays by EV within team-game; chosen plays occupy ranks 1-2 by construction
grp = defaultdict(list)
for r in basefilter(top2): grp[(r["pred_date"], r.get("team"))].append(r)
ranked = defaultdict(list)
for k, v in grp.items():
    # collapse to one entry per PLAYER (a team-mate, not another rung of the same player)
    byp = defaultdict(list)
    for r in v: byp[r["player"]].append(r)
    best = [max(vv, key=lambda r: float(r.get("ev") or 0)) for vv in byp.values()]
    for i, r in enumerate(sorted(best, key=lambda r: -float(r.get("ev") or 0)), start=3):
        ranked[i].append(r)
def rec(sel, lab):
    W=[r for r in sel if b(r)=="W"]; L=[r for r in sel if b(r)=="L"]
    n=len(W)+len(L)
    if n < 4: print(f"  {lab:30s} thin (n={n})"); return
    u=sum(float(r["odds"])-1 for r in W)-len(L)
    print(f"  {lab:30s} {len(W):2d}-{len(L):<2d} {len(W)/n*100:5.1f}%  {u:+7.2f}u  ROI {u/n*100:+6.1f}%  (n={n})")
print("=== DISPLACED PLAYS BY RANK within their team-game (base rungs, one per player) ===")
for i in sorted(ranked):
    rec(ranked[i], f"rank {i} (would be TOP-{i})")
print("\n  FORWARD only:")
FWD = lambda r: str(r["pred_date"]) >= "2026-07-31"
for i in sorted(ranked):
    rec([r for r in ranked[i] if FWD(r)], f"rank {i} forward")
print("\n=== WHAT TOP-3 WOULD ADD (rank 3 only) ===")
r3 = ranked.get(3, [])
chosen = basefilter(kept + mingap)
for lab, sel in (("current book (TOP-2, base rungs)", chosen),
                 ("added by TOP-3 (rank 3 only)", r3),
                 ("combined TOP-3 book", chosen + r3)):
    rec(sel, lab)
print("\n  forward:")
for lab, sel in (("current TOP-2 book", [r for r in chosen if FWD(r)]),
                 ("added by TOP-3", [r for r in r3 if FWD(r)]),
                 ("combined TOP-3 book", [r for r in chosen + r3 if FWD(r)])):
    rec(sel, lab)
print(f"\n  rank-3 plays available on {len(ranked.get(3,[]))} team-games; ranks 4+: {sum(len(v) for i,v in ranked.items() if i>=4)}")
