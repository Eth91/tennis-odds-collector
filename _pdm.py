"""Is the 2.5 rung a full-game points line, or a PERIOD market leaking into the ladder?"""
import fd_collect as FD
AK, BASE, get = FD.AK, FD.BASE, FD.get
page = get("%s/content-managed-page?page=CUSTOM&customPageId=wnba&timezone=America%%2FNew_York&_ak=%s" % (BASE, AK))
evs = page.get("attachments", {}).get("events", {})
eid = next((k for k, v in evs.items() if "Portland" in (v.get("name") or "") or "Fire" in (v.get("name") or "")), None)
print("POR event:", eid, (evs.get(eid) or {}).get("name"))
ev = get("%s/event-page?eventId=%s&_ak=%s&timezone=America%%2FNew_York" % (BASE, eid, AK))
tabs = ev.get("layout", {}).get("tabs", {})
titles = [(t.get("title") if isinstance(t, dict) else str(t)) for t in tabs.values()]
want = [t for t in titles if any(x in (t or "").lower() for x in ("popular","player","prop"))]
seen = {}
for title in want or titles[:3]:
    slug = (title or "").lower().replace(" ", "-").replace("'", "")
    r = get("%s/event-page?eventId=%s&tab=%s&_ak=%s&timezone=America%%2FNew_York" % (BASE, eid, slug, AK)) or {}
    for mid, m in ((r.get("attachments") or {}).get("markets") or {}).items():
        seen.setdefault(mid, (slug, m))
print("\nEVERY market whose name mentions DiLeo:")
for mid,(slug,m) in seen.items():
    nm = m.get("marketName") or ""
    if "DiLeo" not in nm and not any("DiLeo" in (r.get("runnerName") or "") for r in (m.get("runners") or [])):
        continue
    print("  tab=%-16s %r" % (slug, nm))
    for r in (m.get("runners") or [])[:3]:
        pr = ((r.get("winRunnerOdds") or {}).get("trueOdds") or {}).get("decimalOdds",{}).get("decimalOdds")
        print("      %-34s hcap=%-6s odds=%s" % ((r.get("runnerName") or "")[:34], r.get("handicap"), pr))
    rows = list(FD.extract(m, "wnba", "POR"))
    print("      -> extract(): %s" % (rows[:3] if rows else "DROPPED"))
