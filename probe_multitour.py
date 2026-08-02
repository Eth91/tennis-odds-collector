"""Decide which tours can safely join the rating pool, and nail the SG query shape.

OVERLAP IS THE WHOLE QUESTION for multi-tour. Ratings are strokes-vs-field-mean with a two-pass
field-QUALITY correction, and that correction can only calibrate one tour against another through
players who appear in BOTH. A tour with no shared players is a disconnected component: its players
would get ratings on an uncalibrated scale that LOOK comparable to PGA numbers and are not. So
measure overlap before including anything — LPGA in particular is likely disjoint.
"""
import json
import urllib.request
from collections import defaultdict

import pga_birdies as B
D = chr(36)
UA = {"User-Agent": "Mozilla/5.0"}


def espn_players(league, year):
    out = set()
    n_ev = 0
    try:
        u = ("https://site.api.espn.com/apis/site/v2/sports/golf/%s/scoreboard?dates=%d"
             % (league, year))
        j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40))
    except Exception as e:                                          # noqa: BLE001
        return out, 0, str(e)[:40]
    for ev in j.get("events") or []:
        n_ev += 1
        for c in (ev.get("competitions") or [{}])[0].get("competitors") or []:
            nm = ((c.get("athlete") or {}).get("displayName") or "").strip().lower()
            if nm:
                out.add(nm)
    return out, n_ev, None


print("=== ESPN player overlap with PGA (2025) ===")
pga, npga, _ = espn_players("pga", 2025)
print("  pga: %d events, %d distinct players" % (npga, len(pga)))
for lg in ("eur", "champions-tour", "lpga"):
    ps, nev, err = espn_players(lg, 2025)
    if err:
        print("  %-15s unavailable (%s)" % (lg, err))
        continue
    ov = pga & ps
    pct = 100 * len(ov) / max(len(ps), 1)
    verdict = ("SAFE to merge" if pct >= 15 else
               "RISKY — thin bridge" if pct >= 5 else "DISJOINT — do NOT merge")
    print("  %-15s %3d events %4d players | overlap %3d (%.0f%% of its field) -> %s"
          % (lg, nev, len(ps), len(ov), pct, verdict))

print()
print("=== SG query shape ===")


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


for tn in ("StatCategory", "StatLeaderStatCategory", "StatSubCategory", "StatDetails",
           "StatDetail", "StatDetailPlayer", "StatDetailRow"):
    fs = fields(tn)
    if fs:
        print("  %-24s %s" % (tn, [n for n, _ in fs][:12]))

print()
print("  --- statLeaders with the real shape ---")
q = ('query S(%st: TourCode!, %sc: StatCategory!, %sy: Int!) '
     '{statLeaders(tourCode: %st, category: %sc, year: %sy) '
     '{tourCode year categoryHeader subCategories {name statId}}}' % (D, D, D, D, D, D))
d = B.gql(q, {"t": "R", "c": "STROKES_GAINED", "y": 2025})
if d.get("errors"):
    print("   ERR", str(d["errors"])[:220])
else:
    print("   ", json.dumps((d.get("data") or {}).get("statLeaders"))[:600])
