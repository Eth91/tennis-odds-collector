"""Forward record on BASE rungs only (exclude alt-ladder rungs).
Two independent definitions, reported side by side -- if they disagree the split is unreliable:
  A. TWO-WAY main line: odds_other present (the book posted BOTH sides). FanDuel milestone alt
     rungs are one-sided, so odds_other is null/0 on them.
  B. NEAREST EVEN MONEY per (date, player, stat): the primary rung by price, outcome-independent.
Canonical gate throughout: drop tier 'n1' -> current_selection."""
import sqlite3, sys, statistics as st
from collections import defaultdict
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_slip as S
c = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/wnba_ledger.sqlite?mode=ro", uri=True, timeout=30)
c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute("SELECT * FROM predictions")]
overs = [r for r in rows if (r.get("side") or "over")=="over" and (r.get("tier") or "firm")!="n1"]
kept, _ = S.current_selection(overs, commit=False)
def b(r):
    res=str(r.get("result") or "").lower()
    return "VOID" if res=="void" else ("W" if res=="over" else ("L" if res=="under" else "P"))
FWD = lambda r: str(r["pred_date"]) >= "2026-07-31"
def rec(sel, lab):
    W=[r for r in sel if b(r)=="W"]; L=[r for r in sel if b(r)=="L"]
    V=[r for r in sel if b(r)=="VOID"]; P=[r for r in sel if b(r)=="P"]
    n=len(W)+len(L)
    if not n: print(f"  {lab:38s} no graded bets"); return
    u=sum(float(r["odds"])-1 for r in W)-len(L)
    ao=st.mean([float(r["odds"]) for r in W+L])
    print(f"  {lab:38s} {len(W):2d}-{len(L):<2d} {len(W)/n*100:5.1f}%  {u:+7.2f}u  ROI {u/n*100:+6.1f}%"
          f"  avg odds {ao:.2f} (BE {100/ao:.1f}%)  void {len(V)} pend {len(P)}")

# --- definition A: two-way main line
def two_way(r):
    o = r.get("odds_other")
    try: return o is not None and float(o) > 1.0
    except Exception: return False
print("DEFINITION A — two-way main line (odds_other posted)")
print(f"  coverage: {sum(1 for r in kept if two_way(r))}/{len(kept)} tracked rows have odds_other\n")
rec([r for r in kept if FWD(r) and two_way(r)],      "FORWARD  base rungs only")
rec([r for r in kept if FWD(r) and not two_way(r)],  "FORWARD  alt/ladder rungs only")
rec([r for r in kept if FWD(r)],                      "FORWARD  all rungs (for reference)")
print()
rec([r for r in kept if not FWD(r) and two_way(r)],  "PRE-FREEZE base rungs only")

# --- definition B: nearest even money within (date, player, stat)
print("\nDEFINITION B — nearest even money per (date, player, stat)")
g = defaultdict(list)
for r in kept: g[(r["pred_date"], r["player"], r["stat"])].append(r)
base_ids = set()
for k, v in g.items():
    best = min(v, key=lambda r: abs(float(r["odds"]) - 2.0))
    base_ids.add(id(best))
print(f"  {len(g)} player-game-stats -> {len(base_ids)} base rungs, {len(kept)-len(base_ids)} alts\n")
rec([r for r in kept if FWD(r) and id(r) in base_ids],     "FORWARD  base rungs only")
rec([r for r in kept if FWD(r) and id(r) not in base_ids], "FORWARD  alt/ladder rungs only")

print("\n=== do the two definitions agree on the forward base set? ===")
A = {(r["pred_date"], r["player"], r["stat"], r["line"]) for r in kept if FWD(r) and two_way(r)}
B = {(r["pred_date"], r["player"], r["stat"], r["line"]) for r in kept if FWD(r) and id(r) in base_ids}
print(f"  A n={len(A)}  B n={len(B)}  overlap={len(A&B)}  "
      f"agreement={len(A&B)/max(len(A|B),1)*100:.0f}%")
print("\n=== forward base rungs, listed ===")
for r in sorted([r for r in kept if FWD(r) and two_way(r)], key=lambda x: str(x["pred_date"])):
    print(f"  {r['pred_date']}  {str(r['player'])[:19]:19s} {str(r['stat'])[:8]:8s} "
          f"{float(r['line']):5.1f} @ {float(r['odds']):.2f}  {b(r)}")
