import sys; sys.path.insert(0,".")
import wnba_wowy as W
ps=W.players()
S,M,R="Brittney Sykes","Aneesah Morrow","Kiki Rice"
outs=[S,M]
team=[n for n,d in ps.items() if d.get("team")=="TOR"]
lg={n:W.game_log(ps[n]["id"]) for n in team}
pos=lambda n:(ps.get(n) or {}).get("pos"); plays=lambda n:n not in outs
pres={g["game_id"] for o in outs for g in lg[o] if (g.get("min") or 0)>0}
rice={g["game_id"] for g in lg[R] if (g.get("min") or 0)>0}

for cand, stat, line in (("Julie Allemand","ast",5.5),
                         ("Marina Mabrey","pts_ast",22.5),
                         ("Laura Juskaite","pts",9.5)):
    if cand not in lg: print("  %s: no log" % cand); continue
    blog=sorted(lg[cand],key=lambda g:g.get("date") or "")
    elev=[g for g in blog if g["game_id"] not in pres and (g.get("min") or 0)>0]
    if not elev: print("  %-16s no elevated games" % cand); continue
    wr=[g for g in elev if g["game_id"] in rice]; wo=[g for g in elev if g["game_id"] not in rice]
    def val(g):
        if stat=="ast": return g.get("ast") or 0
        if stat=="pts": return g.get("pts") or 0
        return (g.get("pts") or 0)+(g.get("ast") or 0)
    def hr(gs): return "%d/%d" % (sum(1 for g in gs if val(g)>line), len(gs)) if gs else "0/0"
    rw=W.peer_regime_scan(cand, team, outs, lg, pos, plays, min_gap=3.0)
    print("\n  %-16s over %s %s" % (cand, line, stat))
    print("    elevated sample      : %s   (%d games)" % (hr(elev), len(elev)))
    print("    ...Rice OUT (wrong)  : %s" % hr(wo))
    print("    ...Rice PLAYS (real) : %s   <- tonight's lineup" % hr(wr))
    print("    regime warning       : %s" % (("%s, %d/%d match, %sm borrowed" % (rw["peer"],rw["n_match"],rw["n_elev"],rw["gap_min"])) if rw else "NONE"))
