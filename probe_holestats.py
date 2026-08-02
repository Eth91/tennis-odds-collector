"""Is there REAL hole-level course data? Better than inferring green difficulty from residuals.

Deriving "this course rewards putting" from the same residuals we then test on is circular and
low-powered — it is why the course-fit tests kept dying. A DIRECT measurement of green difficulty
would let us test the interaction properly: measure the course, then ask whether good putters
actually beat their rating there.
"""
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


for tn in ("CourseHolesStats", "CourseHoleStats", "HoleStats", "CourseStatsDetails",
           "CourseStatsOverview", "FieldStats"):
    fs = fields(tn)
    if fs:
        print("%-22s %s" % (tn, [("%s:%s" % (n, t)) for n, t in fs][:16]))
print()
print("=== courseHolesStats for the 2025 Rocket Classic (courseId 876) ===")
q = ('query H(%st: ID!, %sc: ID!) {courseHolesStats(tournamentId: %st, courseId: %sc) '
     '{__typename}}' % (D, D, D, D))
d = B.gql(q, {"t": "R2025524", "c": "876"})
print("  typename probe:", json.dumps(d)[:220])
print()
print("=== fieldStats (FieldStatType enum) ===")
d2 = B.gql('{__type(name: "FieldStatType") {enumValues {name}}}')
ev = (((d2.get("data") or {}).get("__type") or {}).get("enumValues") or [])
print("  ", [e["name"] for e in ev][:20])
