import sqlite3, sys, datetime as dt; sys.path.insert(0,".")
import wnba_tonight as T, wnba_wowy as W, wnba_slip as S
N="Marina Mabrey"
print("=== every line FanDuel/DK post for Mabrey tonight ===")
pp=T.posted_props(N) or {}
for stat in sorted(pp):
    rungs=sorted(pp[stat].items())
    print("   %-9s %s" % (stat, [(l, o) for l,(o,u) in rungs][:7]))
print("\n=== what the model flagged (and its tier) ===")
c=sqlite3.connect("wnba_ledger.sqlite"); c.row_factory=sqlite3.Row
today=dt.date.today().isoformat()
rows=[dict(r) for r in c.execute("SELECT * FROM predictions WHERE pred_date>=?",(today,))]
favs=S.fav_keys([r for r in rows if (r.get("side") or "over")=="over"])
for r in rows:
    if r["player"]!=N: continue
    k=(r["pred_date"],r["player"],r["stat"])
    print("   %-8s o%-6s @%-7s ev=%-7s hit=%-6s d_min=%-5s tier=%s"
          % (r["stat"],r["line"],r["odds"],r["ev"],r["proj_hit"],r["d_min"],S.tier_of(r,k in favs)))
print("\n=== her recent SINGLE-stat production (last 10 played) ===")
ps=W.players(); lg=sorted(W.game_log(ps[N]["id"]), key=lambda g:g.get("date") or "")
lg=[g for g in lg if (g.get("min") or 0)>0][-10:]
print("   %-12s %5s %5s %5s %5s  pts+ast" % ("date","min","pts","ast","reb"))
for g in lg:
    print("   %-12s %5s %5s %5s %5s  %s" % (g["date"][:10],g["min"],g.get("pts"),g.get("ast"),g.get("reb"),
          (g.get("pts") or 0)+(g.get("ast") or 0)))
import statistics as st
for key,lab in (("pts","points"),("ast","assists")):
    v=[g.get(key) or 0 for g in lg]
    print("   %-8s mean %.1f  sd %.1f" % (lab, st.mean(v), st.pstdev(v)))
v=[(g.get("pts") or 0)+(g.get("ast") or 0) for g in lg]
print("   %-8s mean %.1f  sd %.1f   <- the combo the model bet" % ("pts_ast", st.mean(v), st.pstdev(v)))
