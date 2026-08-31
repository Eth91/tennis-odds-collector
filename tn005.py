"""TN-005 - the ACE markets specifically: do they exist widely, and what do they cost?

TN-004 sampled 40 matches at random and found ace over/unders on almost none - deep markets are
concentrated on marquee matches. This hunts for them directly, because aces are the best candidate
FanDuel-exclusive market: ace rate is among the most stable player-level stats in tennis, the prior
tennis work already built a serve/return model, and TML carries ATP serve stats back to 1968.

Two questions, in the order that can kill it cheapest:
  COVERAGE  on how many matches does an ace line actually exist? A market on 5% of the board is
            not a programme, whatever its edge.
  COST      what is the hold? TN-004 already found every FD-exclusive market DEARER than
            Pinnacle's 4.7% - no sharp competitor also means no competitive pressure on price.
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
att = d.get("attachments") or {}
evs = att.get("events") or {}
comps = att.get("competitions") or {}
cname = {str(k): str(v.get("name")) for k, v in comps.items()}
matches = [v for v in evs.values() if " v " in str(v.get("name", ""))]

ACE = ("PLAYER_A_ACES", "PLAYER_B_ACES", "TOTAL_ACES_IN_THE_MATCH", "PLAYER_WITH_MOST_ACES",
       "SET_X_ACES", "SET_X_MOST_ACES")
hold = defaultdict(list)
lines = defaultdict(list)
have_ace = 0
checked = 0
depth = []
for v in matches:
    try:
        e = get("%s/event-page?eventId=%s&tab=all&_ak=%s%s" % (B, v.get("eventId"), AK, TZ))
    except Exception:
        continue
    checked += 1
    mk = (e.get("attachments") or {}).get("markets") or {}
    depth.append(len(mk))
    types = {str(m.get("marketType")) for m in mk.values()}
    if types & set(ACE):
        have_ace += 1
    for m in mk.values():
        mt = str(m.get("marketType"))
        if mt not in ACE:
            continue
        rs = [od(r) for r in (m.get("runners") or [])]
        rs = [x for x in rs if x and x > 1.0]
        if len(rs) < 2:
            continue
        tot = sum(1.0 / x for x in rs)
        if 0.9 < tot < 3.0:
            hold[mt].append(100.0 * (tot - 1) / tot)
        for r in (m.get("runners") or []):
            h = r.get("handicap")
            if h:
                lines[mt].append(float(h))
    time.sleep(0.2)

print("matches checked: %d" % checked)
print("matches carrying ANY ace market: %d  (%.0f%% of the board)"
      % (have_ace, 100.0 * have_ace / max(checked, 1)))
print("market depth per match: median %d, max %d" % (st.median(depth), max(depth)))
print()
print("=" * 88)
print("ACE MARKET HOLD")
print("=" * 88)
if not hold:
    print("   NO ace markets with usable two-sided prices were found on the current board.")
else:
    print("   %-30s %7s %9s %9s %10s" % ("market", "books", "median", "min", "typ line"))
    for mt, v in sorted(hold.items(), key=lambda kv: st.median(kv[1])):
        ln = ("%.1f" % st.median(lines[mt])) if lines.get(mt) else "-"
        print("   %-30s %7d %8.1f%% %8.1f%% %10s" % (mt[:30], len(v), st.median(v), min(v), ln))
print()
print("   Pinnacle moneyline 4.73% / set total 4.75%   |   golf tightest 5.2%")
