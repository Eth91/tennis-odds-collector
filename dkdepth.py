import sqlite3, sys; sys.path.insert(0,".")
import wnba_props_db as PDB
c=sqlite3.connect("file:%s?mode=ro"%PDB.props_db(), uri=True)
print("=== alt-rung DEPTH by book (points), latest snapshot per book ===")
q=("SELECT COALESCE(book,'fd') bk, player, COUNT(DISTINCT line) rungs FROM fd_lines "
   "WHERE sport='wnba' AND stat='points' AND side='over' AND COALESCE(live,0)=0 "
   "AND collected_at > datetime('now','-1 day') GROUP BY 1,2")
from collections import defaultdict
d=defaultdict(list)
for bk,plr,n in c.execute(q): d[bk].append(n)
for bk,v in sorted(d.items()):
    v.sort()
    print("   %-4s players=%-4d  median rungs=%s  max=%s" % (bk,len(v),v[len(v)//2],v[-1]))
print("\n=== side-by-side for a few players ===")
q2=("SELECT COALESCE(book,'fd') bk, line FROM fd_lines WHERE sport='wnba' AND stat='points' "
    "AND side='over' AND player=? AND COALESCE(live,0)=0 AND collected_at > datetime('now','-1 day')")
for plr in ("Bridget Carleton","Marina Mabrey","Kahleah Copper"):
    r=defaultdict(set)
    for bk,ln in c.execute(q2,(plr,)): r[bk].add(round(float(ln),1))
    print("   %-18s fd=%s" % (plr, sorted(r.get("fd",[]))))
    print("   %-18s dk=%s" % ("", sorted(r.get("dk",[]))))
print("\n=== EV of laddering, priced on REAL rungs available now ===")
print("   Carleton proj 18.4 (bias-corrected ~17.5); measured clear rate at ~4 headroom = 67%")
for line,price,be in ((13.5,1.9091,52.4),(14.5,2.20,45.5),(19.5,5.10,19.6)):
    for rate,lab in ((0.67,"raw 67%"),(0.56,"bias-adj 56%")):
        print("     o%-6s @%-7s be=%4.1f%%  at %s -> EV %+.2f" % (line,price,be,lab,rate*price-1))
