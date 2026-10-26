#!/usr/bin/env python3
'''GM-007b — is the +0.0954 within-event correlation STABLE across years?

RHO=0.05 is a shipped constant measured three ways in [0.034,0.109]. GM-007 measured +0.0954 on
the cleanest possible sample (R1->R2, full field, zero selection, placebo p=0.000) -- nearly 2x
what the model uses and at the top of that range. Before treating that as a finding it has to
appear in each year separately; a constant that only exists pooled is a pooled artifact.

The prior estimate of +0.039 came from ALL round pairs, which includes cut-selected R3/R4 where
this measures +0.016. Pooling a clean early correlation with a truncated late one lands between
the two, which is exactly where +0.039 sits.
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
print('R1->R2 residual correlation BY YEAR (full field, no selection):')
for y in (2023,2024,2025):
    X,Y,G=[],[],[]
    for eid in ev:
        if int(em[eid][1][:4])!=y: continue
        if (eid,1) not in res or (eid,2) not in res: continue
        com=set(res[(eid,1)])&set(res[(eid,2)])
        if len(com)<40: continue
        for p in com:
            X.append(res[(eid,1)][p]); Y.append(res[(eid,2)][p]); G.append(eid)
    if len(X)<300: print('   %d too few'%y); continue
    X=np.array(X);Y=np.array(Y)
    be=defaultdict(list)
    for x,yy,g in zip(X,Y,G): be[g].append((x,yy))
    rs=[float(np.corrcoef([t[0] for t in v],[t[1] for t in v])[0,1]) for v in be.values() if len(v)>=30]
    se=np.std(rs,ddof=1)/math.sqrt(len(rs))
    print('   %d  corr %+.4f  n=%5d pairs  %3d events  clustered SE %.4f  t=%+.2f'%(y,float(np.corrcoef(X,Y)[0,1]),len(X),len(be),se,float(np.corrcoef(X,Y)[0,1])/se))
print()
print('implied rho from 2-round averages, if rho were constant:')
for rho in (0.05,0.0954):
    print('   rho=%.4f -> corr(mean2, mean2) = %.4f   (GM-007 observed +0.1587)'%(rho, rho/(rho+(1-rho)/2)))
