"""TN-009 - FanDuel tennis hold by market family, read from the tab that actually works.

GOTCHA WORTH RECORDING: an UNKNOWN tab name does not error - it silently returns the 6-market
default. Two earlier passes concluded "no deep boards exist" because they asked for tab=all, which
is not a real tab. The working tab is `popular`; the layout block also names the real tab ids
[319, 109(Popular), 238, 317, 110(Set Markets), 112(Player Markets)].
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
hold = defaultdict(list)
lines = defaultdict(list)
deep = 0
for v in matches:
    try:
        e = get("%s/event-page?eventId=%s&tab=popular&_ak=%s%s" % (B, v.get("eventId"), AK, TZ))
    except Exception:
        continue
    mk = (e.get("attachments") or {}).get("markets") or {}
    if len(mk) >= 20:
        deep += 1
    for m in mk.values():
        mt = str(m.get("marketType"))
        rs = [od(r) for r in (m.get("runners") or [])]
        rs = [x for x in rs if x and x > 1.0]
        if len(rs) < 2:
            continue
        tot = sum(1.0 / x for x in rs)
        if not (0.9 < tot < 3.0):
            continue
        hold[mt].append((100.0 * (tot - 1) / tot, len(rs)))
        for r in (m.get("runners") or []):
            h = r.get("handicap")
            if h:
                lines[mt].append(float(h))
    time.sleep(0.18)

print("matches read via tab=popular: %d ; with a deep board (>=20 markets): %d" % (len(matches), deep))
print()
print("=" * 96)
print("FANDUEL TENNIS HOLD BY MARKET FAMILY  (tab=popular)")
print("=" * 96)
print("%-44s %6s %5s %9s %9s %8s" % ("market type", "books", "runs", "median", "min", "line"))
rows = [(mt, len(v), st.median([x[1] for x in v]), st.median([x[0] for x in v]),
         min(x[0] for x in v)) for mt, v in hold.items() if len(v) >= 3]
for mt, n, nr, med, mn in sorted(rows, key=lambda x: x[3]):
    ln = ("%.1f" % st.median(lines[mt])) if lines.get(mt) else "-"
    tag = "  <- beats Pinnacle 4.7%" if med < 4.7 else ("  reachable" if med < 6.5 else "")
    print("%-44s %6d %5.0f %8.1f%% %8.1f%% %8s%s" % (mt[:44], n, nr, med, mn, ln, tag))
print()
print("   Pinnacle: moneyline 4.73%, set total 4.75%   |   golf tightest family 5.2%")
ace = [r for r in rows if "ACE" in r[0]]
if ace:
    print()
    print("   ACE FAMILY:")
    for mt, n, nr, med, mn in sorted(ace, key=lambda x: x[3]):
        ln = ("%.1f" % st.median(lines[mt])) if lines.get(mt) else "-"
        print("      %-40s n=%3d runners=%.0f  median %.1f%%  min %.1f%%  line %s"
              % (mt[:40], n, nr, med, mn, ln))
