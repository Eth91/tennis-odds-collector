"""EXP-004 RANK DISCOVERY. p_adj rises but hit% does not follow. Does ANY recorded field rank?
Cheap falsification before building anything: rank-correlate every numeric field against the
binary outcome. Fields that rank are candidate re-rankers; if nothing ranks, the ceiling is
selection, not ordering."""
import sys, os, sqlite3, statistics as st
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wnba_slip as S
con = sqlite3.connect("file:wnba_ledger.sqlite?mode=ro", uri=True, timeout=30)
con.row_factory = sqlite3.Row
rows = [dict(r) for r in con.execute("SELECT * FROM predictions")]
keep, _ = S.current_selection(rows)
g = [r for r in keep if r["result"] in ("over", "under")]
won = lambda r: 1 if r["result"] == (r["side"] or "over") else 0
FWD = "2026-07-31"
fields = ["ev","proj_hit","n_elev","proj_min","d_min","d_stat","d_fga","elev_avg","season_avg",
          "odds","vac","total","pace","opp_def","samples","confidence","tier","basis","stale"]
def rankcorr(v, y):
    n=len(v)
    if n<8: return None
    def rk(a):
        idx=sorted(range(n), key=lambda i:a[i]); r=[0]*n
        i=0
        while i<n:
            j=i
            while j+1<n and a[idx[j+1]]==a[idx[i]]: j+=1
            avg=(i+j)/2+1
            for k in range(i,j+1): r[idx[k]]=avg
            i=j+1
        return r
    rv,ry=rk(v),rk(y)
    mv,my=st.mean(rv),st.mean(ry)
    num=sum((a-mv)*(b-my) for a,b in zip(rv,ry))
    d=(sum((a-mv)**2 for a in rv)*sum((b-my)**2 for b in ry))**0.5
    return num/d if d else None
print(f"{'field':12s} {'n(all)':>7s} {'rho_all':>8s} {'n(fwd)':>7s} {'rho_fwd':>8s}  reads")
print("-"*62)
out=[]
for f in fields:
    for scope,rs in (("all",g),("fwd",[r for r in g if r["pred_date"]>=FWD])):
        pass
    va=[(float(r[f]),won(r)) for r in g if r.get(f) is not None and str(r[f]).replace(".","",1).replace("-","",1).isdigit()]
    vf=[(float(r[f]),won(r)) for r in g if r["pred_date"]>=FWD and r.get(f) is not None and str(r[f]).replace(".","",1).replace("-","",1).isdigit()]
    ra=rankcorr([x[0] for x in va],[x[1] for x in va]) if len(va)>=8 else None
    rf=rankcorr([x[0] for x in vf],[x[1] for x in vf]) if len(vf)>=8 else None
    if ra is None and rf is None: continue
    tag=""
    if ra is not None and rf is not None and abs(ra)>0.15 and (ra>0)==(rf>0) and abs(rf)>0.10:
        tag="<== ranks in BOTH cuts"
    print(f"{f:12s} {len(va):7d} {(f'{ra:+.3f}' if ra is not None else '  n/a'):>8s} "
          f"{len(vf):7d} {(f'{rf:+.3f}' if rf is not None else '  n/a'):>8s}  {tag}")
    if tag: out.append((f,ra,rf))
print("\ncandidates that rank in BOTH all-time and forward:", [o[0] for o in out] or "NONE")
