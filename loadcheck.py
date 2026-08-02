import sys, datetime as dt; sys.path.insert(0,".")
import dashboard as D
today = dt.datetime.now(D.ET).date().isoformat()
rows,(w,l,u,pend) = D._load(today)
print("  _load(%s) -> %d rows" % (today, len(rows)))
tod=[r for r in rows if str(r.get("pred_date"))[:10]==today]
print("  of which today's: %d" % len(tod))
for r in sorted(tod,key=lambda x:(x.get("team") or "",x.get("player") or "")):
    print("    %-4s %-18s %-8s o%-6s conf=%-10s side=%s" % (r.get("team"),r.get("player"),r.get("stat"),r.get("line"),r.get("confidence"),r.get("side")))
print()
print("  Puoch present in _load output:", any("Puoch" in str(r.get("player")) for r in rows))
import wnba_slip as S
ov=[r for r in rows if (r.get("side") or "over")=="over"]
keep=S.current_selection(ov)[0]
print("  current_selection on _load rows -> today's keepers:")
for r in keep:
    if str(r.get("pred_date"))[:10]==today:
        print("    KEEP %-4s %-18s %-8s o%s" % (r.get("team"),r.get("player"),r.get("stat"),r.get("line")))
