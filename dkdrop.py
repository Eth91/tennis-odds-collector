import sqlite3, datetime as dt, sys; sys.path.insert(0,".")
import wnba_tonight as T, wnba_props_db as PDB
print("  FRESH_MIN =", T.FRESH_MIN, "minutes")
db=PDB.props_db(); c=sqlite3.connect("file:%s?mode=ro"%db, uri=True)
q=("SELECT player, COALESCE(book,'fd') bk, stat, line, side, odds, collected_at "
   "FROM fd_lines WHERE sport='wnba' AND collected_at > datetime('now','-1 day') AND COALESCE(live,0)=0")
rows=c.execute(q).fetchall()
from collections import defaultdict
byp=defaultdict(list)
for r in rows: byp[r[0]].append(r)
dropped=kept=0; dk_only_lost=[]
for plr, rs in byp.items():
    latest=max(r[6] for r in rs)
    cutoff=(dt.datetime.fromisoformat(latest)-dt.timedelta(minutes=T.FRESH_MIN)).isoformat()
    live_rungs=set(); dead_dk=set()
    for plr_,bk,stat,line,side,odds,ca in rs:
        if line is None: continue
        if ca < cutoff:
            if bk=="dk": dead_dk.add((stat,round(float(line),1)))
            dropped+=1
        else:
            live_rungs.add((stat,round(float(line),1))); kept+=1
    lost=[x for x in dead_dk if x not in live_rungs]
    if lost: dk_only_lost.append((plr,lost))
print("  rows kept %d | rows dropped as stale %d" % (kept, dropped))
print("  players losing a DK-ONLY rung (no other book posts it): %d" % len(dk_only_lost))
for plr,lost in dk_only_lost[:10]:
    print("    %-22s lost rungs: %s" % (plr, sorted(lost)[:5]))
