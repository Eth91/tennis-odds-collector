"""PROFITABILITY, not feasibility. Two measurements decide it:

1. IN-PLAY HOLD (vig). Pre-game WNBA main lines run ~4-5%. If in-play runs 7-9%, every edge must
   clear roughly double the tax before a cent is made.
2. LINE VELOCITY between consecutive 5-min snapshots. If a line moves a lot in 5 minutes, then a
   5-min snapshot CANNOT represent the price you would actually get -- and no backtest built on
   it is executable. This is the deadline-contamination trap in live form.

⚠️ CROSS-BOOK COMPARISON REQUIRES SYNCHRONISED last_update. Two books read minutes apart during a
live game look like arbitrage when they are just stale relative to each other."""
import requests, datetime as dt, statistics as st
from collections import defaultdict
KEY = "64d04fb6d6276d1e7a2783c2b48d0488"
B = "https://api.the-odds-api.com/v4"
EV = "c162d60ca8c8caf4195c3abf4566747a"      # Toronto @ Washington, tip 2026-08-19T23:33Z
TIP = dt.datetime.fromisoformat("2026-08-19T23:33:00+00:00")
SNAPS = ["2026-08-19T23:45:00Z", "2026-08-19T23:55:00Z", "2026-08-20T00:05:00Z",
         "2026-08-20T00:15:00Z", "2026-08-20T00:25:00Z", "2026-08-20T00:40:00Z"]
cost = 0
series = defaultdict(dict)      # (book, player, market) -> {snap_ts: (line, over, under, upd)}
holds = defaultdict(list)
for s in SNAPS:
    r = requests.get(f"{B}/historical/sports/basketball_wnba/events/{EV}/odds",
                     params={"apiKey": KEY, "date": s, "regions": "us",
                             "markets": "player_points,player_rebounds", "oddsFormat": "decimal"},
                     timeout=45)
    cost += int(r.headers.get("x-requests-last") or 0)
    if r.status_code != 200: print(f"  {s}: {r.status_code}"); continue
    j = r.json(); ts = j.get("timestamp"); dd = j.get("data") or {}
    mins = (dt.datetime.fromisoformat(str(ts).replace("Z","+00:00")) - TIP).total_seconds()/60
    nb = 0
    for bk in (dd.get("bookmakers") or []):
        for m in (bk.get("markets") or []):
            pairs = defaultdict(dict)
            for o in (m.get("outcomes") or []):
                pairs[(o.get("description"), o.get("point"))][o.get("name")] = o.get("price")
            for (plr, pt), sides in pairs.items():
                ov, un = sides.get("Over"), sides.get("Under")
                if ov and un and ov > 1 and un > 1:
                    nb += 1
                    hold = (1/ov + 1/un) - 1.0
                    holds[m.get("key")].append(hold)
                    series[(bk.get("key"), plr, m.get("key"))][ts] = (pt, ov, un, bk.get("last_update"))
    print(f"  snap {ts} (+{mins:.0f} min): {nb} two-sided quotes")
print(f"\ncredits spent here: {cost}")
print("\n=== 1. IN-PLAY HOLD (pre-game WNBA main lines are ~4-5%) ===")
for k, v in holds.items():
    if v: print(f"  {k:17s} n={len(v):4d}  median hold {st.median(v)*100:5.2f}%  "
                f"mean {st.mean(v)*100:5.2f}%  min {min(v)*100:5.2f}%")
print("\n=== 2. LINE VELOCITY between consecutive 5-10 min snapshots ===")
moves, jumps = [], 0
for key, snaps in series.items():
    ks = sorted(snaps)
    for a, b in zip(ks, ks[1:]):
        la, oa, ua, _ = snaps[a]; lb, ob, ub, _ = snaps[b]
        if la is None or lb is None: continue
        dl = abs(float(lb) - float(la))
        dp = abs((1/ob) - (1/oa))
        moves.append((dl, dp))
        if dl > 0: jumps += 1
if moves:
    print(f"  {len(moves)} consecutive-snapshot pairs")
    print(f"  LINE changed in {jumps}/{len(moves)} ({jumps/len(moves)*100:.0f}%) of 5-10 min gaps")
    print(f"  median |Δ line| {st.median([m[0] for m in moves]):.2f}   "
          f"median |Δ implied prob| {st.median([m[1] for m in moves])*100:.2f}pp   "
          f"p90 {sorted(m[1] for m in moves)[int(len(moves)*0.9)]*100:.2f}pp")
    print("  ^ if the line moves this much between snapshots, a 5-min snapshot is NOT the price")
    print("    you could have taken, and no backtest on it is executable.")
