import sqlite3, sys; sys.path.insert(0,".")
import wnba_tonight as T, wnba_slip as S
N="Bridget Carleton"
pp=T.posted_props(N) or {}
print("=== every POINTS rung FanDuel currently posts for Carleton ===")
for line,(ov,un) in sorted((pp.get("points") or {}).items()):
    be = (1/ov) if ov else None
    print("   o%-6s over=%-8s under=%-8s  breakeven=%s" % (line, ov or "-", un or "-",
          ("%.1f%%"%(100*be)) if be else "-"))
print("\n=== what the ledger actually flagged ===")
c=sqlite3.connect("wnba_ledger.sqlite"); c.row_factory=sqlite3.Row
import datetime as dt
for r in c.execute("SELECT * FROM predictions WHERE player=? AND pred_date>=?",(N,dt.date.today().isoformat())):
    r=dict(r)
    print("   o%-6s @%-7s ev=%-7s proj_hit=%-6s elev_avg=%-6s d_min=%-5s n_elev=%s conf=%s"
          % (r["line"],r["odds"],r["ev"],r["proj_hit"],r["elev_avg"],r["d_min"],r["n_elev"],r["confidence"]))
    print("   -> TIER inputs: d_min=%s (A needs 3-8), stat=%s (single? %s)"
          % (r["d_min"], r["stat"], r["stat"] in S.TIER_SINGLES))
print("\n=== EV bars the model must clear ===")
print("   OVER_EV_MIN =", T.OVER_EV_MIN, " UNDER_EV_MIN =", T.UNDER_EV_MIN, " LADDER_EV_MIN =", T.LADDER_EV_MIN)
print("\n=== is she a cascade favorite (the other half of tier A)? ===")
rows=[dict(r) for r in c.execute("SELECT * FROM predictions WHERE pred_date>=?",(dt.date.today().isoformat(),))]
favs=S.fav_keys([r for r in rows if (r.get("side") or "over")=="over"])
for r in rows:
    k=(r["pred_date"],r["player"],r["stat"])
    print("   %-18s %-8s fav=%-6s tier=%s" % (r["player"],r["stat"],k in favs,S.tier_of(r,k in favs)))
