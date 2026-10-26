#!/usr/bin/env python3
'''GM-008 — the full round-pair correlation matrix. Is the week effect a CONSTANT?

The model represents within-week correlation as ONE number: a shared per-player week effect of
size RHO. That structure makes a specific, testable claim -- ALL SIX round pairs must correlate
equally. corr(R1,R2) must equal corr(R1,R4) must equal corr(R3,R4).

GM-007 already found two values that cannot both be RHO: R1->R2 = +0.0905 and R3->R4 = +0.0161,
in the SAME no-cut events where neither is touched by cut selection. This maps all six pairs to
see which structure the data actually has:

    equal everywhere            -> a constant week effect; the model is right and RHO is just low
    falls with the LAG          -> autocorrelation (form carries over day to day and fades), NOT a
                                   week effect. A constant rho then over-states R1-R4 dependence
                                   and under-states adjacent rounds.
    falls with the STAGE        -> something about late rounds specifically (contention, pin
                                   positions, players out of it) rather than the gap between them

NO-CUT EVENTS ONLY. In a cut event R3 and R4 exist only for players whose R1-R2 was good enough,
and that truncation moves the correlation for reasons that have nothing to do with golf. No-cut
events are the only place all six pairs are measured on one unselected cohort.
2026 IS THE PROTECTED HOLDOUT AND IS NOT READ.
'''
import hashlib, pickle, sqlite3, math
from collections import defaultdict
import numpy as np
import pga_ruler as RU
KEY=hashlib.sha1(('%s|%s|%s|%s'%(RU.HALF_LIFE_D,RU.K_SHRINK,RU.SIG_SHRINK,RU.MIN_ROUNDS)).encode()).hexdigest()[:12]
fits=pickle.load(open('ratings_cache_%s.pkl'%KEY,'rb')); fd=sorted(fits)
def rf(d):
    lo,hi=0,len(fd)
    while lo<hi:
        m=(lo+hi)//2
        if fd[m]<d: lo=m+1
        else: hi=m
    return fits[fd[lo-1]] if lo>0 else None
con=sqlite3.connect('file:%s?mode=ro'%RU.DB,uri=True,timeout=60)
rows=con.execute("SELECT event_id,event,date,player,rnd,score FROM rounds WHERE date<'2026-01-01'").fetchall()
con.close()
ev=defaultdict(lambda: defaultdict(dict)); em={}
for eid,evn,d,pl,rnd,sc in rows:
    if sc is None: continue
    ev[eid][int(rnd)][pl]=float(sc); em[eid]=(str(evn),str(d))
res=defaultdict(dict)
for eid,byr in ev.items():
    R=rf(em[eid][1])
    if not R: continue
    for rnd,sc in byr.items():
        if len(sc)<40: continue
        m=float(np.mean(list(sc.values())))
        for pl,s in sc.items():
            r=R.get(RU.norm(pl)) or R.get(pl)
            if r is not None: res[(eid,rnd)][pl]=(s-m)-float(r[0])
nocut={eid for eid,byr in ev.items() if 4 in byr and 1 in byr and len(byr[4])>=0.9*len(byr[1]) and len(byr[1])>=40}
print('no-cut events: %d'%len(nocut))
def corr(a,b,pool):
    X,Y,G=[],[],[]
    for eid in pool:
        if (eid,a) not in res or (eid,b) not in res: continue
        com=set(res[(eid,a)])&set(res[(eid,b)])
        if len(com)<30: continue
        for p in com:
            X.append(res[(eid,a)][p]); Y.append(res[(eid,b)][p]); G.append(eid)
    if len(X)<200: return None
    X=np.array(X);Y=np.array(Y)
    be=defaultdict(list)
    for x,y,g in zip(X,Y,G): be[g].append((x,y))
    rs=[float(np.corrcoef([t[0] for t in v],[t[1] for t in v])[0,1]) for v in be.values() if len(v)>=25]
    se=np.std(rs,ddof=1)/math.sqrt(len(rs)) if len(rs)>2 else float('nan')
    return float(np.corrcoef(X,Y)[0,1]), len(X), len(be), se
print()
print('='*88); print('ALL SIX ROUND PAIRS — no-cut events (one unselected cohort)'); print('='*88)
print('   %-10s %-6s %8s %8s %8s %8s'%('pair','lag','corr','n','events','SE'))
bylag=defaultdict(list)
for a,b in ((1,2),(2,3),(3,4),(1,3),(2,4),(1,4)):
    c=corr(a,b,nocut)
    if not c: print('   R%d-R%d    too few'%(a,b)); continue
    r,n,e,se=c
    bylag[b-a].append(r)
    print('   R%d-R%d      %-6d %+8.4f %8d %8d %8.4f'%(a,b,b-a,r,n,e,se))
print()
print('   averaged BY LAG:')
for lag in sorted(bylag):
    print('      lag %d (%d pairs): mean corr %+.4f'%(lag,len(bylag[lag]),float(np.mean(bylag[lag]))))
print()
print('   averaged BY STAGE (pairs starting at round r):')
for st in (1,2,3):
    v=[corr(st,b,nocut) for b in range(st+1,5)]
    v=[x[0] for x in v if x]
    if v: print('      from R%d (%d pairs): mean corr %+.4f'%(st,len(v),float(np.mean(v))))
print()
print('='*88); print('VERDICT'); print('='*88)
print('   A constant week effect of RHO=%.3f predicts the SAME correlation for all six pairs.'%RU.RHO)
print('   Read the two tables above: if the LAG table falls and the STAGE table does not, the')
print('   structure is autocorrelation, not a week effect, and one RHO cannot represent it.')
