"""TN-004 - HOLD CENSUS on FanDuel tennis, by market family. Screen by vig before modelling.

EXP-013 in the golf phase is the reason this runs first: a market whose hold exceeds any plausible
model edge cannot pay, and finding that out after building a model is the expensive order. The
question here is narrower and better posed than in golf, because these markets have NO Pinnacle
counterpart - so there is no sharp reference, which cuts both ways: nothing to benchmark against,
but also no sharp competitor setting the price.

Two-way markets are devigged proportionally. Multi-outcome markets (SET_BETTING, correct scores)
are reported by their overround over all runners, which is the honest number for a market you can
only take one side of.
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
print("matches on board: %d ; sampling up to 40 for the census" % len(matches))

hold = defaultdict(list)
nrun = defaultdict(list)
for v in matches[:40]:
    try:
        e = get("%s/event-page?eventId=%s&tab=all&_ak=%s%s" % (B, v.get("eventId"), AK, TZ))
    except Exception:
        continue
    mk = (e.get("attachments") or {}).get("markets") or {}
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
        nrun[mt].append(len(rs))
    time.sleep(0.2)

print()
print("=" * 94)
print("FANDUEL TENNIS HOLD BY MARKET FAMILY   (books sampled, median hold)")
print("=" * 94)
print("%-44s %7s %8s %8s %8s" % ("market type", "books", "runners", "median", "min"))
rows = []
for mt, v in hold.items():
    if len(v) < 3:
        continue
    rows.append((mt, len(v), st.median(nrun[mt]), st.median(v), min(v)))
for mt, n, nr, med, mn in sorted(rows, key=lambda x: x[3]):
    tag = "  <- reachable" if med < 6 else ("  marginal" if med < 10 else "")
    print("%-44s %7d %8.0f %7.1f%% %7.1f%%%s" % (mt[:44], n, nr, med, mn, tag))

print()
print("   Pinnacle for comparison: moneyline 4.73%, set total 4.75% (TN-001)")
print("   Golf, tightest family (EXP-013): 5.2%")
