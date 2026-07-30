import json
import pga_birdies as B
D = chr(36)


def fields(name):
    d = B.gql('query I(%sn: String!) {__type(name: %sn) {fields {name type {name kind '
              'ofType {name kind ofType {name kind ofType {name}}}}}}}' % (D, D), {"n": name})
    t = (d.get("data") or {}).get("__type")
    if not t:
        return None
    o = []
    for f in t.get("fields") or []:
        ty, ch = f["type"], []
        while ty:
            if ty.get("name"):
                ch.append(ty["name"])
            ty = ty.get("ofType")
        o.append((f["name"], ch[0] if ch else "?"))
    return o


for tn in ("StatDetails", "StatDetailRows", "StatDetailsRow", "StatDetailPlayer",
           "StatLeaderSubCategory", "StatLeaderStat"):
    fs = fields(tn)
    if fs:
        print("%-24s %s" % (tn, [("%s:%s" % (n, t)) for n, t in fs]))
print()
print("=== statLeaders, corrected shape ===")
q = ('query S(%st: TourCode!, %sc: StatCategory!, %sy: Int!) '
     '{statLeaders(tourCode: %st, category: %sc, year: %sy) '
     '{categoryHeader subCategories {displayName stats {statId statTitle}}}}'
     % (D, D, D, D, D, D))
d = B.gql(q, {"t": "R", "c": "STROKES_GAINED", "y": 2025})
if d.get("errors"):
    print("  ERR", str(d["errors"])[:200])
else:
    sl = (d.get("data") or {}).get("statLeaders") or {}
    print("  header:", sl.get("categoryHeader"))
    for sc in sl.get("subCategories") or []:
        print("  sub:", sc.get("displayName"))
        for s in (sc.get("stats") or [])[:10]:
            print("     statId %-8s %s" % (s.get("statId"), s.get("statTitle")))
