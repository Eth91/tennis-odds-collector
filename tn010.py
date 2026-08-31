"""Are the ACE markets genuine multi-outcome books, or stacked alternate lines?

This is the LADDER trap that pga_market exists to prevent: three over/under lines at ~6% each pool
to an overround that reads like a 20% hold, and reporting the pooled number invents a vig the book
never charged. A 46% "hold" on a 4-runner ace market is exactly the shape that demands the check.
"""
import json, urllib.request
AK = "FhMFpcPWXMeyZxOx"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
B = "https://sbapi.ny.sportsbook.fanduel.com/api"
TZ = "&timezone=America%2FNew_York"


def get(u):
    r = urllib.request.Request(u, headers={"User-Agent": UA, "Accept": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=30))


def od(r):
    t = (r.get("winRunnerOdds") or {}).get("trueOdds")
    return (t.get("decimalOdds") or {}).get("decimalOdds") if isinstance(t, dict) else None


d = get("%s/content-managed-page?page=SPORT&eventTypeId=2&pbHorizontal=false&_ak=%s%s" % (B, AK, TZ))
evs = (d.get("attachments") or {}).get("events") or {}
matches = [v for v in evs.values() if " v " in str(v.get("name", ""))]
WANT = ("PLAYER_A_ACES", "PLAYER_B_ACES", "TOTAL_ACES_IN_THE_MATCH", "SET_X_ACES", "SET_BETTING")
shown = set()
for v in matches:
    try:
        e = get("%s/event-page?eventId=%s&tab=popular&_ak=%s%s" % (B, v.get("eventId"), AK, TZ))
    except Exception:
        continue
    mk = (e.get("attachments") or {}).get("markets") or {}
    for m in mk.values():
        mt = str(m.get("marketType"))
        if mt not in WANT or mt in shown:
            continue
        rs = m.get("runners") or []
        if len(rs) < 2:
            continue
        shown.add(mt)
        print("=" * 78)
        print("%s   |   %s" % (mt, str(m.get("marketName"))[:44]))
        tot = 0.0
        for r in rs:
            o = od(r)
            if o:
                tot += 1 / o
            print("   %-40s odds=%-8s handicap=%s" % (str(r.get("runnerName"))[:40], o,
                                                      r.get("handicap")))
        print("   pooled implied sum = %.4f" % tot)
    if len(shown) >= len(WANT):
        break
print()
print("READ: distinct HANDICAPS on same-side runners => stacked alternate lines, pooled hold is")
print("      meaningless. Mutually exclusive BANDS/outcomes => the pooled hold is the real hold.")
