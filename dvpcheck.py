import sys, statistics as st; sys.path.insert(0,".")
import wnba_dvp as DVP, wnba_wowy as W
ps=W.players()
print("=== raw dvp() output for tonight's matchups ===")
for plr,opp,stat in (("Bridget Carleton","LA","points"),("Megan DiLeo","LA","points"),
                     ("Marina Mabrey","GS","points"),("Marina Mabrey","GS","pts_ast"),
                     ("Julie Allemand","GS","assists")):
    pos=(ps.get(plr) or {}).get("position") or (ps.get(plr) or {}).get("pos")
    try: v=DVP.dvp(opp,pos,stat)
    except Exception as e: v="ERR %s"%str(e)[:40]
    print("   %-18s vs %-4s %-8s pos=%-6s -> dvp=%s" % (plr,opp,stat,pos,v))
print("\n=== is the DvP table populated at all? ===")
try:
    t=DVP.dvp_table()
    print("   dvp_table type=%s len=%s" % (type(t).__name__, len(t) if hasattr(t,'__len__') else '?'))
    if isinstance(t,dict):
        ks=list(t)[:5]
        for k in ks: print("     %r -> %r" % (k, t[k]))
        allv=[]
        def walk(o):
            if isinstance(o,dict):
                for v in o.values(): walk(v)
            elif isinstance(o,(int,float)): allv.append(float(o))
        walk(t)
        if allv:
            print("   %d numeric values: min %.4f max %.4f mean %.4f  nonzero %d"
                  % (len(allv),min(allv),max(allv),st.mean(allv),sum(1 for x in allv if abs(x)>1e-9)))
        else: print("   NO numeric values in the table")
except Exception as e:
    print("   dvp_table() FAILED:", str(e)[:120])
print("\n=== what positions do we even have? ===")
pos_counts={}
for n,d in ps.items():
    p=d.get("position") or d.get("pos")
    pos_counts[p]=pos_counts.get(p,0)+1
print("   ", pos_counts)
