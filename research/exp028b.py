"""EXP-028 §30 TRADABLE UNIVERSE. Prerequisite to every repricing claim: at the moment the model
recognised the role change, DID A PRICE ALREADY EXIST? This makes NO predictive claim -- it is
the cheapest falsification. No pre-event price ⇒ the thesis is untestable here and everything
downstream is BLOCKED.

Event timestamp = clv.flagged_at, the only historical event timestamp that persists
(wnba_proj_log upserts on (date,pid) and is a mutable current-state table, not a series).
⚠️ flagged_at is PRICE-DEPENDENT. Acceptable here because we only ask whether a price existed;
any PREDICTIVE test must use price-independent inputs (§19/§20)."""
import sqlite3, datetime as dt, statistics as st
from collections import Counter

tick = sqlite3.connect("file:research/tick_archive.sqlite?mode=ro", uri=True, timeout=180)
days = [r[0] for r in tick.execute("SELECT DISTINCT d FROM obs ORDER BY d")]
print(f"archive days ({len(days)}): {days[0]} .. {days[-1]}   [never trusting BETWEEN alone]")

# resolve clv player names to the archive's exact spelling ONCE -- lower() in a WHERE clause
# defeats the index and would turn 966 lookups into 966 full scans of 3.26M rows.
names = [r[0] for r in tick.execute("SELECT DISTINCT player FROM obs")]
bylow = {}
for n in names: bylow.setdefault(str(n).lower(), n)
def resolve(p):
    k = str(p).lower()
    if k in bylow: return bylow[k]
    for kk, vv in bylow.items():
        if k and (k in kk or kk in k): return vv
    return None

clv = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30)
rows = clv.execute("SELECT date,player,stat,flag_line,flagged_at FROM clv WHERE flagged_at IS NOT NULL "
                   "AND date BETWEEN ? AND ?", (days[0], days[-1])).fetchall()
print(f"{len(rows)} clv events inside the archive's ACTUAL day list\n")

avail = Counter(); leads = []; gaps = []; unresolved = 0
for date, player, stat, fline, fat in rows:
    P = resolve(player)
    if P is None:
        unresolved += 1; avail["player name not in archive (EXCLUDED, not counted as absent)"] += 1
        continue
    pre = tick.execute("SELECT MAX(collected_at) FROM obs WHERE d=? AND player=? AND stat=? "
                       "AND collected_at < ?", (date, P, stat, fat)).fetchone()[0]
    post = tick.execute("SELECT MIN(collected_at) FROM obs WHERE d=? AND player=? AND stat=? "
                        "AND collected_at > ?", (date, P, stat, fat)).fetchone()[0]
    if pre and post:
        avail["PRICE BEFORE and AFTER  (tradable + movement measurable)"] += 1
        a = dt.datetime.fromisoformat(str(pre)); b = dt.datetime.fromisoformat(str(fat))
        c = dt.datetime.fromisoformat(str(post))
        leads.append((b - a).total_seconds()/3600.0); gaps.append((c - a).total_seconds()/3600.0)
    elif pre:
        avail["price BEFORE only  (tradable, movement unobservable)"] += 1
        a = dt.datetime.fromisoformat(str(pre)); b = dt.datetime.fromisoformat(str(fat))
        leads.append((b - a).total_seconds()/3600.0)
    elif post:
        avail["price AFTER only   (NOT tradable at the event)"] += 1
    else:
        avail["no quote for this player-stat-day at all"] += 1

print("=== AVAILABILITY AT THE EVENT ===")
n = len(rows)
for k, v in avail.most_common():
    print(f"  {k:56s} {v:4d}  ({v/n*100:5.1f}%)")
if leads:
    leads.sort()
    print(f"\nstaleness of the last pre-event quote (hours BEFORE the flag), n={len(leads)}:")
    print(f"  median {st.median(leads):6.3f}h   p25 {leads[len(leads)//4]:6.3f}h   "
          f"p75 {leads[3*len(leads)//4]:6.3f}h   max {leads[-1]:6.2f}h")
    print(f"  fresher than 15 min: {sum(1 for x in leads if x <= 0.25)}/{len(leads)}"
          f"  ({sum(1 for x in leads if x <= 0.25)/len(leads)*100:.1f}%)")
if gaps:
    gaps.sort()
    print(f"\nobservation gap straddling the event (pre->post), n={len(gaps)}:")
    print(f"  median {st.median(gaps):6.3f}h   p75 {gaps[3*len(gaps)//4]:6.3f}h   max {gaps[-1]:6.2f}h")
    print(f"  ⚠️ a wide straddle means movement cannot be attributed to the event alone;"
          f" {sum(1 for x in gaps if x > 1)}/{len(gaps)} exceed 1h")
