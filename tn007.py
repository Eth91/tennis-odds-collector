"""TN-007 - the real ACE-LINE vig, measured on DEEP pre-match boards only.

TN-005 read a board dominated by in-play matches, where FanDuel strips the market set to a handful,
so it never saw an ace over/under. Depth is a function of timing: upcoming marquee matches carry
33-43 markets including 9-13 ace markets. This measures the ace lines where they actually exist.
"""
import json, urllib.request, time, statistics as st
from collections import defaultdict
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
deep = []
for v in matches:
    try:
        e = get("%s/event-page?eventId=%s&_ak=%s%s" % (B, v.get("eventId"), AK, TZ))
    except Exception:
        continue
    mk = (e.get("attachments") or {}).get("markets") or {}
    if len(mk) >= 20:
        deep.append((v, mk))
    time.sleep(0.15)
print("matches with a DEEP pre-match board (>=20 markets): %d of %d" % (len(deep), len(matches)))

hold = defaultdict(list)
lines = defaultdict(list)
for v, mk in deep:
    for m in mk.values():
        mt = str(m.get("marketType"))
        rs = [od(r) for r in (m.get("runners") or [])]
        rs = [x for x in rs if x and x > 1.0]
        if len(rs) < 2:
            continue
        tot = sum(1.0 / x for x in rs)
        if not (0.9 < tot < 3.0):
            continue
        hold[mt].append(100.0 * (tot - 1) / tot)
        for r in (m.get("runners") or []):
            h = r.get("handicap")
            if h:
                lines[mt].append(float(h))

print()
print("=" * 92)
print("HOLD ON DEEP PRE-MATCH BOARDS, every market family")
print("=" * 92)
print("%-44s %6s %9s %9s %9s" % ("market type", "books", "median", "min", "typ line"))
rows = [(mt, len(v), st.median(v), min(v)) for mt, v in hold.items() if len(v) >= 3]
for mt, n, med, mn in sorted(rows, key=lambda x: x[2]):
    ln = ("%.1f" % st.median(lines[mt])) if lines.get(mt) else "-"
    tag = "  <- CHEAPEST TIER" if med < 5 else ("  reachable" if med < 6.5 else "")
    print("%-44s %6d %8.1f%% %8.1f%% %9s%s" % (mt[:44], n, med, mn, ln, tag))
print()
print("   Pinnacle: moneyline 4.73%, set total 4.75%   |   golf tightest family 5.2%")
print()
ace = [r for r in rows if "ACE" in r[0]]
if ace:
    print("   ACE FAMILY ONLY:")
    for mt, n, med, mn in sorted(ace, key=lambda x: x[2]):
        print("      %-40s n=%3d  median %.1f%%  min %.1f%%" % (mt[:40], n, med, mn))
