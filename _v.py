import wnba_tonight as W
from collections import Counter
inj = W.injuries()
print("total:", len(inj), Counter(inj.values()))
print("NEWS(rank1):", sorted(W.NEWS_OUTS))
print("RW(rank3)  :", sorted(W.RW_FALLBACK_OUTS))
print("confirmed  :", len(W.CONFIRMED_OUT_TODAY))
for n in ("Aaliyah Edwards","Isabelle Harrison","Nyara Sabally","Saniya Rivers","Kiki Rice"):
    print("   %-20s %s" % (n, inj.get(n)))
