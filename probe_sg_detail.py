"""Confirm the two paid-looking features are actually retrievable free."""
import json
import pga_birdies as B
D = chr(36)


def enum(name):
    d = B.gql('query I(%sn: String!) {__type(name: %sn) {enumValues {name}}}' % (D, D),
              {"n": name})
    t = (d.get("data") or {}).get("__type") or {}
    return [e["name"] for e in (t.get("enumValues") or [])]


print("StatCategory values:", enum("StatCategory")[:20])
print("HistoricalOddsId  :", enum("HistoricalOddsId")[:14])
print("OddsTimeType      :", enum("OddsTimeType")[:10])
print()
print("=" * 72)
print("1. STROKES-GAINED by category, free?")
cats = enum("StatCategory")
sgcat = next((c for c in cats if "STROKE" in c.upper() or "SG" == c.upper()), None)
print("   trying category:", sgcat or cats[:5])
q = ('query S(%st: TourCode!, %sc: StatCategory!, %sy: Int!) '
     '{statLeaders(tourCode: %st, category: %sc, year: %sy) '
     '{title stats {statId statTitle players {playerName statValue}}}}' % (D, D, D, D, D, D))
d = B.gql(q, {"t": "R", "c": sgcat or cats[0], "y": 2025})
if d.get("errors"):
    print("   ERR", str(d["errors"])[:200])
else:
    sl = (d.get("data") or {}).get("statLeaders") or {}
    stats = sl.get("stats") or []
    print("   title:", sl.get("title"), "| %d stats returned" % len(stats))
    for s in stats[:8]:
        pl = s.get("players") or []
        print("     %-10s %-42s top: %s %s"
              % (s.get("statId"), str(s.get("statTitle"))[:42],
                 (pl[0].get("playerName") if pl else "-"),
                 (pl[0].get("statValue") if pl else "")))
print()
print("=" * 72)
print("2. HISTORICAL ODDS via oddsGraph, free?")
tid = "R2025524"
for mkt in (enum("HistoricalOddsId") or ["WIN"])[:3]:
    q2 = ('query O(%st: String!, %sm: HistoricalOddsId!) '
          '{oddsGraph(tournamentId: %st, marketId: %sm) '
          '{playerId points {timestamp odds}}}' % (D, D, D, D))
    d2 = B.gql(q2, {"t": tid, "m": mkt})
    if d2.get("errors"):
        print("   %-22s ERR %s" % (mkt, str(d2["errors"])[:110]))
    else:
        g = (d2.get("data") or {}).get("oddsGraph")
        print("   %-22s OK  %s" % (mkt, json.dumps(g)[:180] if g else "empty"))
