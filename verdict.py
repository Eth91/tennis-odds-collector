import sys; sys.path.insert(0,".")
import wnba_wowy as W
ps=W.players(); A,R,S,M="Julie Allemand","Kiki Rice","Brittney Sykes","Aneesah Morrow"
lg={n:W.game_log(ps[n]["id"]) for n in (A,R,S,M)}
pres={g["game_id"] for l in (lg[S],lg[M]) for g in l if (g.get("min") or 0)>0}
al=sorted(lg[A],key=lambda g:g.get("date") or "")
elev=[g for g in al if g["game_id"] not in pres and (g.get("min") or 0)>0]
rice={g["game_id"] for g in lg[R] if (g.get("min") or 0)>0}
LINE=5.5
def hit(gs): return sum(1 for g in gs if (g.get("ast") or 0) > LINE)
print("=== how often did she actually CLEAR 5.5 assists? ===")
print("  all 11 elevated games      : %d/%d  (%.0f%%)" % (hit(elev),len(elev),100*hit(elev)/len(elev)))
wr=[g for g in elev if g["game_id"] in rice]; wo=[g for g in elev if g["game_id"] not in rice]
print("  ...Rice OUT   (wrong lineup): %d/%d" % (hit(wo),len(wo)))
print("  ...Rice PLAYS (tonight's)   : %d/%d   <- the sub-sample that matters" % (hit(wr),len(wr)))
for g in wr: print("        %s  %sm  %s ast  (%.3f ast/min)" % (g["date"][:10],g["min"],g["ast"],(g["ast"] or 0)/(g["min"] or 1)))
print("\n=== minutes sensitivity: she is assist-EFFICIENT, so it hinges on minutes ===")
rate=sum((g["ast"] or 0) for g in wr)/sum((g["min"] or 0) for g in wr)
print("  her ast/min with Rice on the floor: %.3f" % rate)
for m in (16,18,20,22,24,26):
    print("    %2d min -> %.1f projected assists   %s" % (m, m*rate, "OVER" if m*rate>LINE else "under"))
print("\n  Rice: back 2g of a 56-day absence, 8.5 min under her 28.5 norm, trend +6.0 -> tonight is game 3.")
print("  Last game Rice hit 23 min and Allemand fell to 22.")
