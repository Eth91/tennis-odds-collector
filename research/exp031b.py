"""EXP-031 §14/§15 BOOK LEAD-LAG on the FULL archive.

WHY THIS AND NOT MORE EVENT TESTS. EXP-029/030 are sample-bound at n=73 and the backups are
exhausted, so no amount of cleverness adds events. This question uses ALL 3.26M observations:
when one book moves, does the other follow, and is one systematically first?

⚠️ ASYMMETRY IS THE ONLY VALID EVIDENCE. Two books reacting independently to the same news each
look like they 'lead' the other at similar rates. Only a large gap between fd->dk and dk->fd
indicates real lead-lag structure. A symmetric result means shared news, not a leader.

Reads day-by-day (11 sequential scans) rather than per-key lookups: the box is a 2-core VM
already at load 7, where 8,709 indexed lookups went I/O-bound at 3% CPU and made no progress."""
import sqlite3, datetime as dt, statistics as st, math
from collections import Counter, defaultdict

tick = sqlite3.connect("file:research/tick_archive.sqlite?mode=ro", uri=True, timeout=900)
days = [r[0] for r in tick.execute("SELECT DISTINCT d FROM obs ORDER BY d")]
print(f"days: {days}", flush=True)
WIN = 3600.0
def p_of(o):
    o = float(o); return 1.0/o if o > 1.0 else None
def changes(seq):
    out, prev = [], None
    for t, v in seq:
        if v is None: continue
        if prev is not None and abs(v - prev) > 1e-9: out.append((t, v - prev))
        prev = v
    return out

lead = Counter(); lags = defaultdict(list); nkeys = 0; nboth = 0
for d in days:
    cur = tick.execute("SELECT player, stat, line, side, book, collected_at, odds FROM obs "
                       "WHERE d=? ORDER BY player, stat, line, side, book, collected_at", (d,))
    grp = defaultdict(lambda: {"fd": [], "dk": []})
    n = 0
    for player, stat, line, side, book, ca, odds in cur:
        if book not in ("fd", "dk"): continue
        grp[(player, stat, line, side)][book].append(
            (dt.datetime.fromisoformat(str(ca)), p_of(odds)))
        n += 1
    for key, by in grp.items():
        if len(by["fd"]) < 4 or len(by["dk"]) < 4: continue
        nboth += 1
        cf, cd = changes(by["fd"]), changes(by["dk"])
        if not cf or not cd: continue
        nkeys += 1
        for A, B, tag in ((cf, cd, "fd->dk"), (cd, cf, "dk->fd")):
            for t, delta in A:
                best = None
                for tb, db in B:
                    s = (tb - t).total_seconds()
                    if s <= 0: continue
                    if s > WIN: break
                    if db * delta > 0: best = s; break
                if best is not None:
                    lead[tag] += 1; lags[tag].append(best)
                else:
                    lead[tag + "!"] += 1
    print(f"  {d}: {n:7d} rows, {len(grp):5d} keys, {nboth:5d} both-book, {nkeys:5d} usable", flush=True)

print(f"\nkeys with both books AND a price change in each: {nkeys}\n")
print("=== DOES A MOVE IN ONE BOOK GET FOLLOWED BY THE OTHER (same direction, <=60min)? ===")
for tag in ("fd->dk", "dk->fd"):
    f, nf = lead[tag], lead[tag + "!"]
    if f + nf:
        L = lags[tag]
        med = f"{st.median(L)/60:.1f} min" if L else "n/a"
        print(f"  {tag}: {f}/{f+nf} followed ({f/(f+nf)*100:5.1f}%)   median lag {med}")
a, an, b, bn = lead["fd->dk"], lead["fd->dk!"], lead["dk->fd"], lead["dk->fd!"]
if (a + an) and (b + bn):
    pa, pb = a/(a+an), b/(b+bn)
    pp = (a+b)/(a+an+b+bn)
    se = math.sqrt(pp*(1-pp)*(1/(a+an)+1/(b+bn))) if 0 < pp < 1 else 1e-12
    z = (pa-pb)/se
    print(f"\n  ASYMMETRY: fd-leads {pa*100:.1f}%  vs  dk-leads {pb*100:.1f}%   "
          f"gap {(pa-pb)*100:+.1f}pp   z={z:+.2f}")
    print(f"  -> {'ONE BOOK LEADS' if abs(z) > 3 else 'SYMMETRIC: shared news, no exploitable leader'}")
    if lags["fd->dk"] and lags["dk->fd"]:
        print(f"  median lag fd->dk {st.median(lags['fd->dk'])/60:.1f} min   "
              f"dk->fd {st.median(lags['dk->fd'])/60:.1f} min")
