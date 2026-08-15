"""EXP-001 odds-timeline coverage. Q: when do WNBA props FIRST exist?
If the earliest broad coverage is T-4h, no model improvement earlier than that is monetizable."""
import sqlite3
from collections import defaultdict
c = sqlite3.connect("file:basketball_wnba_odds_hist.sqlite?mode=ro", uri=True, timeout=30)
c.row_factory = sqlite3.Row
ORDER = ["opener", "t240", "t120", "t60", "t45", "tip"]
HRS = {"opener": 48.0, "t240": 4.0, "t120": 2.0, "t60": 1.0, "t45": 0.75, "tip": 0.48}

print("=== per-snapshot coverage (2025-05-01+, the decay-pull span) ===")
print(f"{'snap':8s} {'h-to-tip':>9s} {'events':>7s} {'players':>8s} {'quotes':>9s} {'mkts':>5s}")
base = None
for s in ORDER:
    r = c.execute("SELECT COUNT(DISTINCT event_id), COUNT(DISTINCT player), COUNT(*), "
                  "COUNT(DISTINCT market) FROM props WHERE snap_kind=? AND game_date>='2025-05-01'",
                  (s,)).fetchone()
    if s == "t240":
        base = r[0]
    print(f"{s:8s} {HRS[s]:9.2f} {r[0]:7d} {r[1]:8d} {r[2]:9,} {r[3]:5d}")
print(f"\n  (t240 = {base} events is the denominator: the widest span pulled at every lead)")

print("\n=== FIRST appearance: earliest snapshot holding ANY prop, per event ===")
ev_snaps = defaultdict(set)
for r in c.execute("SELECT event_id, snap_kind FROM props WHERE game_date>='2025-05-01' "
                   "GROUP BY event_id, snap_kind"):
    ev_snaps[r["event_id"]].add(r["snap_kind"])
first = defaultdict(int)
for ev, snaps in ev_snaps.items():
    for s in ORDER:
        if s in snaps:
            first[s] += 1
            break
tot = len(ev_snaps)
run = 0
for s in ORDER:
    run += first[s]
    print(f"  first seen at {s:7s} ({HRS[s]:5.2f}h): {first[s]:4d} events  "
          f"cumulative {run:4d}/{tot} = {run/tot*100:5.1f}%")

print("\n=== how many events have a line at EACH lead (the monetizable window) ===")
for s in ORDER:
    n = sum(1 for snaps in ev_snaps.values() if s in snaps)
    print(f"  {s:7s} ({HRS[s]:5.2f}h): {n:4d}/{tot} = {n/tot*100:5.1f}% of events")
