"""EXP-027 IS PR-002 EVEN CAPTURABLE? The shadow arm has logged 0 rows in 2 days on a */20 cron
that IS installed and IS firing. Before waiting on n>=40 forever, verify the instrument.

This checks the INSTRUMENT, not the hypothesis: no hit rate, ROI or outcome is computed or
inspected. PR-002's promotion bar is untouched.

THE DECISIVE QUESTION: when do WNBA props FIRST appear relative to tip? If books post 4h out,
a T-8h..T-13h capture window can never fill, and PR-002 is structurally untestable on this
path -- regardless of what the retrospective decay curve said."""
import sqlite3, sys, datetime as dt
from collections import defaultdict
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
fd = sqlite3.connect("file:wnba_lines.sqlite?mode=ro", uri=True, timeout=60)
print("A. FIRST APPEARANCE of each (player, stat, line) quote, per day in the 3-day buffer")
first = {}
for player, stat, line, ca in fd.execute(
        "SELECT player, stat, line, MIN(collected_at) FROM fd_lines WHERE sport='wnba' "
        "AND side='over' AND (live IS NULL OR live=0) AND stat IN ('points','rebounds','assists') "
        "GROUP BY substr(collected_at,1,10), player, stat, line"):
    first[(player, stat, line, str(ca)[:10])] = str(ca)
print(f"   {len(first)} distinct player-stat-line-days in the buffer")

import wnba_tonight as T
try:
    tips = T.tip_times()
except Exception as e:                                                # noqa: BLE001
    tips = {}; print(f"   tip_times unavailable: {str(e)[:50]}")
print(f"   tip_times() returned {len(tips)} team(s) for today\n")

print("B. LEAD-TIME DISTRIBUTION -- hours between first quote and the day's EARLIEST tip.")
print("   Using each day's earliest tip is CONSERVATIVE: it understates lead for later games,")
print("   so if this says props are late, they are late for certain.")
byday = defaultdict(list)
for (player, stat, line, d), ca in first.items():
    byday[d].append(ca)
for d in sorted(byday):
    times = sorted(byday[d])
    n = len(times)
    print(f"   {d}: {n:5d} quotes, earliest {times[0][11:16]}Z  median {times[n//2][11:16]}Z  "
          f"latest {times[-1][11:16]}Z")
print("\n   WNBA tips are typically 23:00-02:00Z. A T-8h..T-13h window is therefore ~10:00-18:00Z.")
inwin = sum(1 for d in byday for t in byday[d] if "10:00" <= t[11:16] <= "18:00")
tot = sum(len(v) for v in byday.values())
print(f"   quotes first appearing inside 10:00-18:00Z: {inwin}/{tot} ({inwin/tot*100:.1f}%)")
print(f"   quotes first appearing AFTER 18:00Z (too late for the window): "
      f"{sum(1 for d in byday for t in byday[d] if t[11:16] > '18:00')}/{tot}")

print("\nC. CAPTURE FUNNEL -- how many candidates survive each gate, window check REMOVED")
import wnba_wowy as W, wnba_stint_wowy as SW
pl = W.players(); inj = T.injuries()
outs_by = defaultdict(list)
for n, st in inj.items():
    p = pl.get(n)
    if p and "out" in str(st).lower() and (p.get("min", 0) >= 15):
        outs_by[p["team"]].append(n)
print(f"   teams with a >=15-min player OUT: {len(outs_by)}  {dict((k, len(v)) for k, v in outs_by.items())}")
src = sqlite3.connect("file:wnba_stints.sqlite?mode=ro", uri=True, timeout=30)
mem = sqlite3.connect(":memory:"); src.backup(mem); src.close()
for ddl in ("CREATE INDEX i1 ON onfloor(player, game_date)",
            "CREATE INDEX i3 ON pairs(player, mate, game_date)"):
    try: mem.execute(ddl)
    except Exception: pass                                            # noqa: BLE001
mem.row_factory = sqlite3.Row
slate = dt.datetime.now(dt.timezone(dt.timedelta(hours=-4))).date().isoformat()
f = defaultdict(int)
for team, outs in outs_by.items():
    for outp in outs:
        mates = [n for n, v in pl.items() if v.get("team") == team and n != outp and (v.get("gp") or 0) >= 5]
        starters = SW.projected_starters(mem, mates, slate, outs=outs)
        for ben in mates:
            f["mates"] += 1
            if ben not in starters: continue
            f["projected starter"] += 1
            nwo, _, _ = SW.game_level_n_without(mem, ben, outp, slate)
            if nwo >= 2: continue
            f["n_without<2 (new ground)"] += 1
            try: props = T.posted_props(ben) or {}
            except Exception: props = {}                              # noqa: BLE001
            if not props: continue
            f["has posted props"] += 1
            for stat in ("rebounds", "assists", "points"):
                for line, pr in (props.get(stat) or {}).items():
                    dec = pr[0] if isinstance(pr, (list, tuple)) else pr
                    if not dec or not (1.3 <= float(dec) <= 6.0): continue
                    f["priced rung"] += 1
for k in ("mates", "projected starter", "n_without<2 (new ground)", "has posted props", "priced rung"):
    print(f"   {k:28s} {f[k]:5d}")
