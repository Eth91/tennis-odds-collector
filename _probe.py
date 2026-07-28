"""Where does FanDuel keep Saniya Rivers' points 6.5? The user found it via the site search
bar; our event-page tab walk never sees it. Enumerate EVERY market on the CON event and show
which mention her, and whether our parser would accept the market name.
"""
import re

import fd_collect as FD

AK = FD.AK
BASE = FD.BASE
get = FD.get

print("BASE:", BASE)
evs = get("%s/content-managed-page?page=CUSTOM&customPageId=wnba&_ak=%s"
          "&timezone=America%%2FNew_York" % (BASE, AK))
att = (evs or {}).get("attachments", {})
events = att.get("events", {}) or {}
print("wnba events found: %d" % len(events))
target = None
for eid, e in events.items():
    nm = e.get("name") or ""
    print("   %-12s %s" % (eid, nm))
    if "Valkyries" in nm or "Mercury" in nm or "Dream" in nm or "Wings" in nm:
        target = eid
if not target and events:
    target = list(events)[0]
print("\nprobing event:", target, (events.get(target) or {}).get("name"))

ev = get("%s/event-page?eventId=%s&_ak=%s&timezone=America%%2FNew_York" % (BASE, target, AK))
_raw = ((ev or {}).get("layout") or {}).get("tabs") or []
tabs = [t if isinstance(t, str) else (t.get("slug") or t.get("name")) for t in _raw]
tabs = [t for t in tabs if t]
print("tabs: %s" % tabs)

seen_markets = {}
for slug in [None] + tabs:
    url = ("%s/event-page?eventId=%s&_ak=%s&timezone=America%%2FNew_York" % (BASE, target, AK)
           if slug is None else
           "%s/event-page?eventId=%s&tab=%s&_ak=%s&timezone=America%%2FNew_York"
           % (BASE, target, slug, AK))
    r = get(url) or {}
    mk = (r.get("attachments", {}) or {}).get("markets", {}) or {}
    for mid, m in mk.items():
        seen_markets.setdefault(mid, (slug, m))

print("total distinct markets across all tabs: %d" % len(seen_markets))
print()
print("=== markets mentioning a sample player ===")
hits = 0
for mid, (slug, m) in seen_markets.items():
    nm = m.get("marketName") or ""
    runners = [(r.get("runnerName") or "") for r in (m.get("runners") or [])]
    blob = nm + " " + " ".join(runners)
    if "Rivers" not in blob and "Thomas" not in blob and "Copper" not in blob:
        continue
    hits += 1
    print("  tab=%-22s market=%r" % (slug, nm))
    for r in (m.get("runners") or [])[:6]:
        pr = ((r.get("winRunnerOdds") or {}).get("trueOdds") or {}).get(
            "decimalOdds", {}).get("decimalOdds")
        print("       runner=%-38s handicap=%-6s odds=%s" % (
            (r.get("runnerName") or "")[:38], r.get("handicap"), pr))
print("  (%d markets mention her)" % hits)

print()
print("=== every DISTINCT market name on this event (to spot what we filter out) ===")
names = sorted({(m.get("marketName") or "") for _, (_, m) in seen_markets.items()})
for n in names:
    star = "  <-- points-ish" if re.search(r"point", n, re.I) else ""
    print("   %s%s" % (n, star))
