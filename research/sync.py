"""Is the FD/DK in-play gap REAL, or are the books just stale relative to each other?
During a live game a 3-minute read difference is a different game state. This is the
deadline-contamination trap in live form: an 'arb' that is really a timestamp mismatch."""
import requests, datetime as dt, statistics as st
from collections import defaultdict
KEY = "64d04fb6d6276d1e7a2783c2b48d0488"
B = "https://api.the-odds-api.com/v4"
EV = "c162d60ca8c8caf4195c3abf4566747a"
r = requests.get(f"{B}/historical/sports/basketball_wnba/events/{EV}/odds",
                 params={"apiKey": KEY, "date": "2026-08-20T00:15:00Z", "regions": "us",
                         "markets": "player_points,player_rebounds", "oddsFormat": "decimal"}, timeout=45)
print(f"cost={r.headers.get('x-requests-last')} used={r.headers.get('x-requests-used')}")
j = r.json(); snap = dt.datetime.fromisoformat(str(j["timestamp"]).replace("Z","+00:00"))
dd = j.get("data") or {}
print(f"\nsnapshot {j['timestamp']} — per-book staleness AT that instant:")
quotes = defaultdict(dict)
for bk in (dd.get("bookmakers") or []):
    upd = dt.datetime.fromisoformat(str(bk["last_update"]).replace("Z","+00:00"))
    skew = (snap - upd).total_seconds()
    print(f"  {bk['key']:14s} last_update {str(bk['last_update'])[11:19]}  ({skew:+.0f}s before snapshot)")
    for m in (bk.get("markets") or []):
        sides = defaultdict(dict)
        for o in (m.get("outcomes") or []):
            sides[(o.get("description"), o.get("point"))][o.get("name")] = o.get("price")
        for k, v in sides.items():
            if v.get("Over"): quotes[(m["key"],)+k][bk["key"]] = (v["Over"], v.get("Under"), skew)
print("\nrungs quoted by BOTH books at this snapshot:")
gaps, arbs = [], 0
for k, bks in quotes.items():
    if len(bks) < 2: continue
    (b1, v1), (b2, v2) = list(bks.items())[:2]
    p1, p2 = 1/v1[0], 1/v2[0]
    gaps.append(abs(p1-p2))
    best_over = max(v1[0], v2[0]); best_under = max(x for x in (v1[1], v2[1]) if x) if (v1[1] and v2[1]) else None
    arb = (1/best_over + 1/best_under - 1) if best_under else None
    if arb is not None and arb < 0: arbs += 1
    print(f"  {k[1][:16]:16s} {k[0]:15s} {k[2]}  {b1}={v1[0]:.2f} {b2}={v2[0]:.2f}  "
          f"|Δp|={abs(p1-p2)*100:5.2f}pp  skew {abs(v1[2]-v2[2]):.0f}s"
          + (f"  ARB {(-arb)*100:.2f}%" if arb is not None and arb < 0 else ""))
if gaps:
    print(f"\n  median cross-book |Δ implied prob| = {st.median(gaps)*100:.2f}pp on {len(gaps)} shared rungs")
    print(f"  apparent arbitrages: {arbs}/{len(gaps)}")
    print("  ⚠️ compare against the 4.27pp the line moves BETWEEN snapshots: if the cross-book gap")
    print("     is the same size as the time-drift, it is staleness, not disagreement.")
