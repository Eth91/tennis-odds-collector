"""EXP-019 do the OTHER situation variables predict the BET OUTCOME?
EXP-018 showed news-age predicts CLV but not money. Test the remaining cheap, interpretable
situation variables against OUTCOME on the 433-row graded pool (5x the tracked sample).
No p_adj/proj_hit/proj as a selector anywhere."""
import sys, os, sqlite3, statistics as st, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
c = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30); c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute(
    "SELECT * FROM clv WHERE flag_line IS NOT NULL AND actual IS NOT NULL AND flag_over IS NOT NULL")]
for r in rows:
    r["won"] = float(r["actual"]) > float(r["flag_line"])
    r["ncas"] = len([x for x in (r["out_player"] or "").split(",") if x.strip()])
    r["moved"] = (float(r["close_line"])-float(r["flag_line"])) if r.get("close_line") else None
print(f"n={len(rows)} graded\n")
def rec(v, lbl, minn=25):
    if len(v) < minn: return None
    w = sum(1 for r in v if r["won"]); u = sum((float(r["flag_over"])-1) if r["won"] else -1 for r in v)
    print(f"   {lbl:24s} n={len(v):3d}  {w}-{len(v)-w} = {w/len(v)*100:5.1f}%  {u:+7.2f}u  ROI {u/len(v)*100:+6.1f}%")
    return w/len(v)
def chrono(key, label, buckets):
    print(f"-- {label} --")
    ds = sorted({r["date"] for r in rows}); mid = ds[len(ds)//2]
    res = {}
    for bl, sel in buckets:
        full = rec([r for r in rows if sel(r)], bl)
        e = [r for r in rows if sel(r) and r["date"] < mid]
        l = [r for r in rows if sel(r) and r["date"] >= mid]
        if full is not None and len(e) >= 20 and len(l) >= 20:
            he = sum(1 for r in e if r["won"])/len(e); hl = sum(1 for r in l if r["won"])/len(l)
            res[bl] = (full, he, hl)
            print(f"       chrono: early {he*100:5.1f}%  later {hl*100:5.1f}%")
    print()
    return res
chrono(None, "CASCADE COMPLEXITY", [("1 out", lambda r: r["ncas"]==1),
                                    ("2 out", lambda r: r["ncas"]==2),
                                    ("3+ out", lambda r: r["ncas"]>=3)])
chrono(None, "MARKET", [("points", lambda r: r["stat"]=="points"),
                        ("rebounds", lambda r: r["stat"]=="rebounds"),
                        ("assists", lambda r: r["stat"]=="assists")])
chrono(None, "FLAG LINE LEVEL", [("line <= 5.5", lambda r: float(r["flag_line"])<=5.5),
                                 ("5.5 < line <= 10.5", lambda r: 5.5<float(r["flag_line"])<=10.5),
                                 ("line > 10.5", lambda r: float(r["flag_line"])>10.5)])
print("-- DID THE LINE MOVE? (market confirmation as a SELECTOR, not a target) --")
mv=[r for r in rows if r["moved"] is not None]
a=rec([r for r in mv if r["moved"]>0],"line moved UP (toward us)")
b=rec([r for r in mv if r["moved"]==0],"line did NOT move")
d=rec([r for r in mv if r["moved"]<0],"line moved DOWN (against us)")
if a and d:
    x=[r for r in mv if r["moved"]>0]; y=[r for r in mv if r["moved"]<0]
    pp=(sum(1 for r in x if r["won"])+sum(1 for r in y if r["won"]))/(len(x)+len(y))
    se=math.sqrt(pp*(1-pp)*(1/len(x)+1/len(y)))
    print(f"\n   up-vs-down gap {(a-d)*100:+.1f}pp  z={(a-d)/se if se else 0:.2f}")
