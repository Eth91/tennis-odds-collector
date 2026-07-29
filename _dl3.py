import wnba_tonight as T, wnba_wowy as W, wnba_context as CTX, wnba_dvp as DVP
pl = W.players(); who="Megan DiLeo"
blog = W.game_log(pl[who]["id"]); barker = W.game_log(pl["Sarah Ashlee Barker"]["id"])
w = W.wowy_multi(blog, [barker])
out_dm=[{g["date"][:10]: g.get("min",0) for g in barker}]
vac={"points":10.7,"rebounds":pl["Sarah Ashlee Barker"]["reb"],"assists":pl["Sarah Ashlee Barker"]["ast"]}
mus=T.tonight_matchups(); ctx=CTX.matchup_context("POR", mus.get("POR",""), CTX.game_lines(), CTX.team_rates())
pos=pl[who].get("position"); opp=mus.get("POR","")
print("opp=%s pos=%s  dvp(points)=%.4f" % (opp, pos, DVP.dvp(opp,pos,"pts") if opp and pos else 0))
for label, kw in (("full call", dict(out_logs=out_dm, opp=opp, pos=pos)),
                  ("no dvp (opp/pos None)", dict(out_logs=out_dm)),
                  ("no out_logs", dict(opp=opp, pos=pos))):
    e = T.prop_edges(who, blog, 27.0, w, vac, ctx, **kw)
    print("%-24s -> %d spot(s): %s" % (label, len(e),
          [(x["stat"], x["line"], round(x["ev"]*100,1), x["side"], x.get("stale")) for x in e]))
# what does the raw (pre-selection) list look like? call the selector directly
import inspect
src = inspect.getsource(T._select_player_bets)
print("\nLADDER/selection constants:", {k:getattr(T,k) for k in dir(T) if k in
      ("LADDER_MAX","LADDER_GAP","HIGH_EV","POINTS_PREF_MARGIN","THIN_SAMPLE_N","BIG_JUMP_MIN","COLD_START_MARGIN","ROLE_GUARD_MINN")})
