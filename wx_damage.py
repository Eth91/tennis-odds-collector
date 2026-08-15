#!/usr/bin/env python3
"""How much of the weather data is pulled from the WRONG PLACE? Quantify before fixing.

_course_latlon geocodes a bare CITY NAME, which is ambiguous, and caches ONE coordinate per
TOURNAMENT NAME, which is wrong for any event that rotates venues. Both failure modes are present
and neither is loud:

    Masters Tournament        44.3106, -69.7795   Augusta MAINE, not Georgia      ~1,300 km
    Memorial Tournament       53.3331,  -6.2489   Dublin IRELAND, not Ohio        ~5,600 km
    U.S. Open                 50.9040,  -1.4043   Southampton ENGLAND             wrong continent
    The Open                  42.5847, -87.8212   Kenosha WISCONSIN               wrong continent
    Puerto Rico Open         -32.0350, -52.0986   Rio Grande BRAZIL               wrong HEMISPHERE
    Genesis Scottish Open     43.3037, -70.7334   North Berwick MAINE             wrong continent
    Hero World Challenge      40.6984, -74.4015   New Jersey, not the Bahamas
    PGA Championship          39.9868, -75.4010   one coord for a ROTATING major

A wrong coordinate does not fail; it returns real weather for somewhere else. Southern-hemisphere
Brazil in March is the opposite season from Puerto Rico. That contaminated wind then went into the
`ix` interaction table AND into the production wind_factor fit, and it is the obvious reason
weather interactions have been hard to find: the regressor is partly another continent's noise.

This measures the blast radius. It changes nothing.
"""
import math
import sqlite3
from collections import defaultdict

import pga_context as C

# tournament -> (correct lat, lon) for the ones checkable by inspection. Rotating majors get
# None: no single coordinate can be right for them, which is itself the finding.
TRUTH = {
    "Masters Tournament": (33.5030, -82.0199),          # Augusta National, GA
    "The Memorial Tournament pres. by Workday": (40.1462, -83.1524),   # Muirfield Village, OH
    "the Memorial Tournament pres. by Workday": (40.1462, -83.1524),
    "Puerto Rico Open": (18.3800, -65.8000),            # Rio Grande, PR
    "Genesis Scottish Open": (56.0400, -2.8300),        # North Berwick, Scotland
    "Hero World Challenge": (24.9900, -77.5300),        # Albany, Bahamas
    "The Open": (55.5500, -4.6500),                     # Royal Troon 2024, Scotland
    "U.S. Open": None,                                  # rotates
    "PGA Championship": None,                           # rotates
    "Cadillac Championship": None,
}


def km(a, b):
    if not a or not b:
        return None
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(h))


ll = C._cache().get("latlon") or {}
print("=" * 92)
print("DISTANCE FROM THE REAL VENUE, where the real venue is unambiguous")
print("=" * 92)
bad = set()
for nm, truth in TRUTH.items():
    got = ll.get(nm)
    if not got:
        continue
    if truth is None:
        print("   %-42s ROTATING VENUE — one cached coord cannot be right" % nm[:42])
        bad.add(nm)
        continue
    d = km((got[0], got[1]), truth)
    flag = "WRONG" if d and d > 100 else "ok"
    print("   %-42s %8.1f km off   %s" % (nm[:42], d or -1, flag))
    if d and d > 100:
        bad.add(nm)

# blast radius in the research table
ixc = sqlite3.connect("file:/home/ubuntu/pga_interactions.sqlite?mode=ro", uri=True)
pm = sqlite3.connect("file:pga_model.sqlite?mode=ro", uri=True)
ev_name = {}
for eid, evn in pm.execute("SELECT DISTINCT event_id, event FROM rounds"):
    ev_name[str(eid)] = str(evn)
pm.close()


def ckey(name):
    return " ".join(sorted(w for w in str(name or "").lower().split() if len(w) > 3))


badkeys = {ckey(b) for b in bad}
tot = wx = contaminated = 0
per = defaultdict(int)
for eid, w in ixc.execute("SELECT event_id, wind FROM ix"):
    tot += 1
    if w is None:
        continue
    wx += 1
    nm = ev_name.get(str(eid), "")
    if ckey(nm) in badkeys:
        contaminated += 1
        per[nm] += 1
ixc.close()
print("\n" + "=" * 92)
print("BLAST RADIUS in the ix interaction table")
print("=" * 92)
print("   rows total %d | with wind %d | from a KNOWN-WRONG coordinate %d (%.1f%% of weather rows)"
      % (tot, wx, contaminated, 100 * contaminated / max(wx, 1)))
for nm, c in sorted(per.items(), key=lambda x: -x[1]):
    print("      %-46s %5d rows" % (nm[:46], c))
print("\n   NOTE this counts only the events checkable by inspection. The bare-city geocode is")
print("   ambiguous everywhere, so the true contamination rate is a LOWER BOUND.")
print("   The same cache feeds the production wind_factor. Reported, NOT modified — the")
print("   simulator is frozen and repairing it in place would change live inputs.")
