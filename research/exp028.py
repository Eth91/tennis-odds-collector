"""EXP-028 §30 TRADABLE UNIVERSE. Before any repricing claim, answer the prerequisite: at the
moment the model recognised the role change, DID A PRICE ALREADY EXIST?

Four outcomes are possible per §31. This experiment can only distinguish "price exists" from
"price does not exist" -- it makes NO claim about predictability. It is deliberately the cheapest
falsification: if no tradable price precedes the event, the whole thesis is untestable on this
data and everything downstream is BLOCKED.

Information timestamp = clv.flagged_at (the only historical event timestamp that persists;
wnba_proj_log is an UPSERT on (date,pid) and therefore a mutable current-state table, not a
series -- see DATA RISKS).

⚠️ flagged_at is PRICE-DEPENDENT (the flag needs EV >= threshold, which reads the price). That is
acceptable HERE because this experiment only asks whether a price existed, not whether anything
predicts movement. Any predictive test must use the price-independent signal instead (§19/§20)."""
import sqlite3, statistics as st
from collections import Counter, defaultdict

tick = sqlite3.connect("file:research/tick_archive.sqlite?mode=ro", uri=True, timeout=120)
print("=== §37 TICK ARCHIVE VALIDATION (never trust BETWEEN alone) ===")
print("  rows            :", tick.execute("SELECT COUNT(*) FROM obs").fetchone()[0])
print("  oldest / newest :", tick.execute("SELECT MIN(collected_at),MAX(collected_at) FROM obs").fetchone())
print("  distinct dates  :", tick.execute("SELECT COUNT(DISTINCT d) FROM obs").fetchone()[0])
print("  distinct snaps  :", tick.execute("SELECT COUNT(DISTINCT collected_at) FROM obs").fetchone()[0])
print("  books           :", tick.execute("SELECT book,COUNT(*) FROM obs GROUP BY book").fetchall())
days = [r[0] for r in tick.execute("SELECT DISTINCT d FROM obs ORDER BY d")]
print("  day list        :", days)
LO, HI = days[0], days[-1]

clv = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30)
rows = clv.execute(
    "SELECT date, player, stat, flag_line, flagged_at, actual, flag_over FROM clv "
    "WHERE flagged_at IS NOT NULL AND date BETWEEN ? AND ?", (LO, HI)).fetchall()
print(f"\n{len(rows)} clv events inside the archive's ACTUAL day list")

avail = Counter(); leads = []; postgap = []; nolead = []
percase = []
for date, player, stat, fline, fat, actual, fover in rows:
    pl = str(player).lower()
    pre = tick.execute(
        "SELECT MAX(collected_at) FROM obs WHERE d=? AND lower(player)=? AND stat=? "
        "AND collected_at < ?", (date, pl, stat, fat)).fetchone()[0]
    post = tick.execute(
        "SELECT MIN(collected_at) FROM obs WHERE d=? AND lower(player)=? AND stat=? "
        "AND collected_at > ?", (date, pl, stat, fat)).fetchone()[0]
    anyq = tick.execute("SELECT COUNT(*) FROM obs WHERE d=? AND lower(player)=? AND stat=?",
                        (date, pl, stat)).fetchone()[0]
    if anyq == 0:
        avail["no quote for this player-stat-day at all"] += 1; continue
    if pre and post: avail["PRICE BEFORE **and** AFTER the event (tradable + measurable)"] += 1
    elif pre:        avail["price before only (tradable, movement unobservable)"] += 1
    elif post:       avail["price after only (NOT tradable at the event)"] += 1; nolead.append((date, player, stat))
    else:            avail["quotes exist but none on either side"] += 1
    if pre:
        h = (dtp := None)
        import datetime as dt
        a = dt.datetime.fromisoformat(str(pre)); b = dt.datetime.fromisoformat(str(fat))
        leads.append((b - a).total_seconds() / 3600.0)
    if pre and post:
        import datetime as dt
        a = dt.datetime.fromisoformat(str(pre)); c = dt.datetime.fromisoformat(str(post))
        postgap.append((c - a).total_seconds() / 3600.0)
print("\n=== AVAILABILITY AT THE EVENT ===")
for k, v in avail.most_common():
    print(f"  {k:55s} {v:4d}  ({v/len(rows)*100:5.1f}%)")
if leads:
    leads.sort()
    print(f"\n  age of the last pre-event quote (hours before the flag):")
    print(f"    median {st.median(leads):6.2f}h   p25 {leads[len(leads)//4]:6.2f}h   "
          f"p75 {leads[3*len(leads)//4]:6.2f}h   max {leads[-1]:6.2f}h")
    print(f"    quotes staler than 6h: {sum(1 for x in leads if x > 6)}/{len(leads)} "
          f"-- a very stale pre-price weakens 'the book had not adjusted'")
if postgap:
    postgap.sort()
    print(f"\n  observation gap straddling the event (pre->post, hours):")
    print(f"    median {st.median(postgap):6.2f}h   p75 {postgap[3*len(postgap)//4]:6.2f}h")
    print(f"    ⚠️ movement measured across a wide gap cannot be attributed to the event alone")
