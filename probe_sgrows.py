import json
import pga_birdies as B
D = chr(36)


def fields(name):
    d = B.gql('query I(%sn: String!) {__type(name: %sn) {fields {name type {name kind '
              'ofType {name kind ofType {name}}}}}}' % (D, D), {"n": name})
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


for tn in ("StatDetailsRow", "StatDetailPlayer", "StatDetailsPlayerRow"):
    fs = fields(tn)
    if fs:
        print("%-22s %s" % (tn, [("%s:%s" % (n, t)) for n, t in fs]))
print()
# standard PGA Tour SG stat ids
SG = {"02567": "SG: Off-the-Tee", "02568": "SG: Approach", "02569": "SG: Around-the-Green",
      "02564": "SG: Putting", "02674": "SG: Tee-to-Green", "02675": "SG: Total"}
q = ('query SD(%st: TourCode!, %ss: String!, %sy: Int!) '
     '{statDetails(tourCode: %st, statId: %ss, year: %sy) '
     '{statTitle tourAvg rows {... on StatDetailsPlayer {playerId playerName '
     'stats {statName statValue}}}}}' % (D, D, D, D, D, D))
for sid, lbl in list(SG.items())[:3]:
    d = B.gql(q, {"t": "R", "s": sid, "y": 2025})
    if d.get("errors"):
        print("  %-6s %-22s ERR %s" % (sid, lbl, str(d["errors"])[:140]))
        continue
    sd = (d.get("data") or {}).get("statDetails") or {}
    rows = sd.get("rows") or []
    print("  %-6s %-22s title=%r tourAvg=%s rows=%d"
          % (sid, lbl, sd.get("statTitle"), sd.get("tourAvg"), len(rows)))
    for r in rows[:3]:
        print("      ", json.dumps(r)[:170])
