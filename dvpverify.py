import sys, statistics as st; sys.path.insert(0,".")
import wnba_dvp as DVP
print("=== combos now resolve ===")
for team,pos,stat in (("GS","G","pts_ast"),("GS","G","pts"),("GS","G","ast"),
                      ("LA","F","pra"),("LA","F","pts_reb"),("TOR","G","reb_ast")):
    print("   dvp(%-4s,%s,%-8s) = %+0.4f" % (team,pos,stat,DVP.dvp(team,pos,stat)))
print("\n   check additivity: GS/G pts_ast should equal pts + ast")
a=DVP.dvp("GS","G","pts"); b=DVP.dvp("GS","G","ast"); c=DVP.dvp("GS","G","pts_ast")
print("     %+0.4f + %+0.4f = %+0.4f   vs pts_ast %+0.4f   %s" % (a,b,a+b,c,"OK" if abs(a+b-c)<1e-9 else "MISMATCH"))
print("\n=== matchup_note now fires for combos ===")
for team,pos,stat in (("GS","G","pts_ast"),("LA","F","pra"),("TOR","G","pts_reb")):
    print("   %-4s %s %-8s -> %s" % (team,pos,stat,DVP.matchup_note(team,pos,stat)))
print("\n=== how big is the nudge in real points? (elev_avg += dvp * proj_min) ===")
for team,pos,stat in (("GS","G","pts_ast"),("LA","F","pra")):
    d=DVP.dvp(team,pos,stat)
    print("   %-4s %s %-8s dvp=%+0.4f/min -> %+0.2f over 30 min" % (team,pos,stat,d,d*30))
