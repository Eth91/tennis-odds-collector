"""Can we get strokes-gained by category and multi-tour rounds for FREE?

Both from sources we ALREADY query legitimately:
  * the PGA Tour orchestrator GraphQL (public key, already used for scorecards + courseStats)
  * ESPN's public scoreboard (already used for the rounds crawl)

If SG-by-category is in the orchestrator, blind spot #2 from the DataGolf audit costs nothing.
If tourCode accepts other tours, blind spot #5 (974 players below MIN_ROUNDS) costs nothing too.
Only the historical ODDS archive would remain genuinely unavailable.
"""
import json
import pga_birdies as B

D = chr(36)

print("=" * 74)
print("A. does the orchestrator expose STROKES-GAINED / stats queries?")
q = ('{__schema {queryType {fields {name args {name type {name kind ofType {name}}}}}}}')
d = B.gql(q)
qf = (((d.get("data") or {}).get("__schema") or {}).get("queryType") or {}).get("fields") or []
if not qf:
    print("   introspection blocked:", str(d.get("errors"))[:150])
else:
    hits = [f for f in qf
            if any(t in f["name"].lower() for t in ("stat", "sg", "strokes", "perf"))]
    print("   %d query fields total; stat-ish ones:" % len(qf))
    for f in hits:
        args = ", ".join("%s:%s" % (a["name"], a["type"].get("name")
                                    or (a["type"].get("ofType") or {}).get("name"))
                         for a in f.get("args") or [])
        print("     %s(%s)" % (f["name"], args))

print()
print("=" * 74)
print("B. tourCode — can schedule() serve OTHER tours? (multi-tour rounds for free)")
for code, label in (("R", "PGA Tour"), ("H", "Korn Ferry"), ("E", "DP World/Euro"),
                    ("S", "Champions"), ("M", "PGA Tour Americas"), ("Y", "?")):
    try:
        r = B.gql('{schedule(tourCode: "%s", year: "2025") {completed '
                  '{tournaments {id tournamentName}}}}' % code)
        if r.get("errors"):
            print("   %-3s %-18s ERR %s" % (code, label, str(r["errors"])[:60]))
            continue
        ts = []
        for g in ((r.get("data") or {}).get("schedule") or {}).get("completed") or []:
            ts += g.get("tournaments") or []
        pre = sorted({str(t.get("id"))[:1] for t in ts})
        print("   %-3s %-18s %3d events  id-prefix %s  e.g. %s"
              % (code, label, len(ts), pre, (ts[0]["tournamentName"][:30] if ts else "-")))
    except Exception as e:                                          # noqa: BLE001
        print("   %-3s %-18s EXC %s" % (code, label, str(e)[:60]))

print()
print("=" * 74)
print("C. ESPN — other golf leagues on the endpoint we already crawl?")
import urllib.request
for lg in ("pga", "eur", "champions-tour", "korn-ferry", "lpga"):
    u = ("https://site.api.espn.com/apis/site/v2/sports/golf/%s/scoreboard?dates=2025" % lg)
    try:
        j = json.load(urllib.request.urlopen(urllib.request.Request(
            u, headers={"User-Agent": "Mozilla/5.0"}), timeout=25))
        ev = j.get("events") or []
        print("   %-16s %3d events 2025" % (lg, len(ev)))
    except Exception as e:                                          # noqa: BLE001
        print("   %-16s unavailable (%s)" % (lg, str(e)[:40]))
