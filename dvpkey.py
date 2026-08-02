import sys; sys.path.insert(0,".")
import wnba_dvp as DVP
t=DVP.dvp_table()
print("   table keys:", sorted(t.keys()))
for stat in ("points","pts","rebounds","reb","assists","ast","threes","fg3m"):
    print("   dvp('LA','F',%-10r) = %s" % (stat, DVP.dvp("LA","F",stat)))
