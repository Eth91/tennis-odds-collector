"""TEAM markets in-play vs PLAYER props. Game totals/spreads are the books' highest-volume in-play
markets and normally carry a much thinner hold than player props. If any live angle exists, this
is where -- so measure the tax before recommending anything."""
import requests, statistics as st
from collections import defaultdict
KEY = "64d04fb6d6276d1e7a2783c2b48d0488"
B = "https://api.the-odds-api.com/v4"
EV = "c162d60ca8c8caf4195c3abf4566747a"
holds = defaultdict(list); cost = 0
for snap in ("2026-08-19T23:50:00Z", "2026-08-20T00:10:00Z", "2026-08-20T00:30:00Z"):
    r = requests.get(f"{B}/historical/sports/basketball_wnba/events/{EV}/odds",
                     params={"apiKey": KEY, "date": snap, "regions": "us",
                             "markets": "totals,spreads,h2h", "oddsFormat": "decimal"}, timeout=45)
    cost += int(r.headers.get("x-requests-last") or 0)
    if r.status_code != 200: continue
    dd = r.json().get("data") or {}
    for bk in (dd.get("bookmakers") or []):
        for m in (bk.get("markets") or []):
            sides = defaultdict(dict)
            for o in (m.get("outcomes") or []):
                sides[o.get("point")][o.get("name")] = o.get("price")
            for pt, v in sides.items():
                ps = [p for p in v.values() if p and p > 1]
                if len(ps) == 2:
                    holds[m["key"]].append(sum(1/p for p in ps) - 1.0)
print(f"credits: {cost}\n")
print("=== IN-PLAY HOLD by market type ===")
for k, v in sorted(holds.items()):
    if v:
        print(f"  {k:9s} n={len(v):3d}  median {st.median(v)*100:5.2f}%  min {min(v)*100:5.2f}%")
print(f"  {'player_*':9s}          median  7.00-7.14%  (measured earlier)")
print("\n=== EDGE REQUIRED TO BREAK EVEN (two-sided, hold split evenly) ===")
for lab, h in (("pre-game main line", 0.045), ("in-play team total", st.median(holds.get("totals", [0.05]))),
               ("in-play player prop", 0.070)):
    print(f"  {lab:22s} hold {h*100:4.1f}%  ->  posted implied prob on a coin flip "
          f"{(0.5*(1+h))*100:.1f}%  ->  need {(0.5*h)*100:.2f}pp of TRUE edge")
