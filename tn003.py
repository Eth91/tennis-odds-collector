"""TN-003 - what does FanDuel actually OFFER on a tennis match, beyond the 3 default markets?

The default event-page returns only MATCH_BETTING and the two "to win at least 1 set" markets.
Prior work established FanDuel hides lines behind TABS, and hides some on no tab at all (only the
separate search host returns those). This enumerates the tab space for one marquee match, because
the user's real question is which markets exist on FD that Pinnacle does not price - those are the
ones with no sharp reference, and therefore the only place a soft edge can still live.
"""
import json, urllib.request, time
from collections import defaultdict

AK = "FhMFpcPWXMeyZxOx"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
B = "https://sbapi.ny.sportsbook.fanduel.com/api"
TZ = "&timezone=America%2FNew_York"


def get(u):
    r = urllib.request.Request(u, headers={"User-Agent": UA, "Accept": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=30))


d = get("%s/content-managed-page?page=SPORT&eventTypeId=2&pbHorizontal=false&_ak=%s%s" % (B, AK, TZ))
att = d.get("attachments") or {}
evs = att.get("events") or {}
matches = [v for v in evs.values() if " v " in str(v.get("name", ""))]
# pick a marquee match - deepest markets
target = None
for want in ("Alcaraz", "Sabalenka", "Swiatek", "Djokovic", "Sinner"):
    for v in matches:
        if want in str(v.get("name")):
            target = v
            break
    if target:
        break
target = target or matches[0]
eid = target.get("eventId")
print("probing: %s  (eventId %s)" % (target.get("name"), eid))
print()

TABS = ["", "popular", "all", "match", "sets", "games", "handicap", "totals", "correct-score",
        "set-betting", "player-props", "props", "specials", "alternate", "alternate-lines",
        "match-lines", "game-lines", "set-lines", "outright", "more-wagers", "in-play"]
seen = {}
tabinfo = defaultdict(set)
for tab in TABS:
    tq = "&tab=%s" % tab if tab else ""
    try:
        e = get("%s/event-page?eventId=%s%s&_ak=%s%s" % (B, eid, tq, AK, TZ))
    except Exception as ex:
        print("   tab %-16s FAIL %s" % (tab or "(default)", str(ex)[:34]))
        continue
    mk = (e.get("attachments") or {}).get("markets") or {}
    new = 0
    for mid, m in mk.items():
        mt = str(m.get("marketType"))
        tabinfo[tab or "(default)"].add(mt)
        if mid not in seen:
            seen[mid] = m
            new += 1
    print("   tab %-16s markets=%-4d new=%d" % (tab or "(default)", len(mk), new))
    time.sleep(0.2)

print()
print("=" * 88)
print("UNION OF ALL MARKET TYPES FOUND: %d markets" % len(seen))
print("=" * 88)
types = defaultdict(int)
for m in seen.values():
    types[str(m.get("marketType"))] += 1
for t, n in sorted(types.items()):
    ex = next(m for m in seen.values() if str(m.get("marketType")) == t)
    print("   %-42s x%-3d  e.g. %s" % (t[:42], n, str(ex.get("marketName"))[:38]))
