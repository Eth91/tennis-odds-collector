import wnba_tonight as T, wnba_wowy as W, wnba_context as CTX
pl = W.players(); who = "Megan DiLeo"
blog = W.game_log(pl[who]["id"]); barker = W.game_log(pl["Sarah Ashlee Barker"]["id"])
w = W.wowy_multi(blog, [barker])
mus = T.tonight_matchups()
ctx = CTX.matchup_context("POR", mus.get("POR",""), CTX.game_lines(), CTX.team_rates())

orig = T._select_player_bets
captured = {}
def spy(out):
    captured["in"] = list(out)
    res = orig(out)
    captured["out"] = list(res)
    return res
T._select_player_bets = spy

T.prop_edges(who, blog, 27.0, w, {"points":10.7,"rebounds":5.0,"assists":2.0}, ctx,
             out_logs=[{g["date"][:10]: g.get("min",0) for g in barker}],
             opp=mus.get("POR",""), pos=pl[who].get("position"))
T._select_player_bets = orig

print("RAW spots produced by prop_edges BEFORE selection: %d" % len(captured.get("in", [])))
for s in captured.get("in", []):
    print("   %-9s o%-5g @%-6.2f ev %+6.1f%% side=%-5s stale=%-5s band_pilot=%s orig_line=%s"
          % (s["stat"], s["line"], s["dec"], s["ev"]*100, s["side"], s.get("stale"),
             s.get("band_pilot"), s.get("orig_line")))
print("AFTER selection: %d" % len(captured.get("out", [])))
pp = T.posted_props(who) or {}
print("\nposted 'points' ladder as the model sees it:")
for ln,(o,u) in sorted((pp.get("points") or {}).items()):
    print("   line %-5g over %-8s under %s" % (ln, o, u))
