import json
import pga_birdies as B
D = chr(36)


def fields(name):
    d = B.gql('query I(%sn: String!) {__type(name: %sn) {fields {name type {name kind '
              'ofType {name kind ofType {name}}}}}}' % (D, D), {"n": name})
    t = (d.get("data") or {}).get("__type")
    if not t:
        return None
    out = []
    for f in t.get("fields") or []:
        ty, chain = f["type"], []
        while ty:
            if ty.get("name"):
                chain.append(ty["name"])
            ty = ty.get("ofType")
        out.append((f["name"], chain[0] if chain else "?"))
    return out


for tn in ("StatLeaderCategory", "StatLeaders", "StatLeader", "StatLeaderPlayer"):
    fs = fields(tn)
    if fs:
        print("%s: %s" % (tn, [n for n, _t in fs][:14]))

print()
print("=== pull STROKES_GAINED leaders, 2025 PGA ===")
q = ('query S(%st: TourCode!, %sc: StatCategory!, %sy: Int!) '
     '{statLeaders(tourCode: %st, category: %sc, year: %sy) '
     '{category stats {statId title players {player {displayName} statValue}}}}'
     % (D, D, D, D, D, D))
d = B.gql(q, {"t": "R", "c": "STROKES_GAINED", "y": 2025})
if d.get("errors"):
    print("ERR", str(d["errors"])[:260])
else:
    sl = (d.get("data") or {}).get("statLeaders") or {}
    print("category:", sl.get("category"))
    for s in (sl.get("stats") or [])[:8]:
        pl = s.get("players") or []
        top = pl[0] if pl else {}
        print("  %-8s %-46s  top: %-22s %s"
              % (s.get("statId"), str(s.get("title"))[:46],
                 ((top.get("player") or {}).get("displayName") or "-"), top.get("statValue")))
