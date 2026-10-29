"""EXP-031 §14/§15 BOOK LEAD-LAG. EXP-029/030 are sample-bound (n=73 events; the backups are
exhausted). This asks a question the FULL archive can answer with millions of observations:

    when one book moves, does the other follow -- and is one systematically first?

If neither book leads, repricing has no exploitable structure and the thesis weakens independently
of the small event sample. If one leads, that is a predictable repricing signal with real n.

METHOD. For each (day, player, stat, line, side) quoted by BOTH books, build each book's odds-CHANGE
series in implied probability. For every change in book A, ask whether B makes a same-direction
change within the following window, and record the lag. Then compare A->B against B->A.

⚠️ ASYMMETRY IS THE ONLY VALID EVIDENCE. Both books reacting to the same external news would make
each look like it 'leads' the other about equally. A genuine leader shows A->B >> B->A."""
import sqlite3, datetime as dt, statistics as st, math
from collections import Counter, defaultdict

tick = sqlite3.connect("file:research/tick_archive.sqlite?mode=ro", uri=True, timeout=600)
print("keys quoted by BOTH books:", flush=True)
keys = tick.execute(
    "SELECT d, player, stat, line, side FROM obs GROUP BY d,player,stat,line,side "
    "HAVING COUNT(DISTINCT book)=2").fetchall()
print(f"  {len(keys)}", flush=True)

WIN = 3600.0                      # look up to 1h ahead for a follow
def p_of(o):
    o = float(o); return 1.0/o if o > 1.0 else None

def changes(seq):
    """(timestamp, delta) for each actual price change; identical consecutive quotes are not events."""
    out = []
    prev = None
    for t, o in seq:
        v = p_of(o)
        if v is None: continue
        if prev is not None and abs(v - prev[1]) > 1e-9:
            out.append((t, v - prev[1]))
        prev = (t, v)
    return out

lead = Counter(); lags = defaultdict(list); nkeys = 0
for i, (d, player, stat, line, side) in enumerate(keys):
    rows = tick.execute("SELECT collected_at, odds, book FROM obs WHERE d=? AND player=? AND stat=? "
                        "AND line=? AND side=? ORDER BY collected_at",
                        (d, player, stat, line, side)).fetchall()
    by = {"fd": [], "dk": []}
    for t, o, b in rows:
        if b in by: by[b].append((dt.datetime.fromisoformat(str(t)), o))
    if len(by["fd"]) < 4 or len(by["dk"]) < 4: continue
    cf, cd = changes(by["fd"]), changes(by["dk"])
    if not cf or not cd: continue
    nkeys += 1
    for A, B, tag in ((cf, cd, "fd->dk"), (cd, cf, "dk->fd")):
        for t, delta in A:
            fol = [(tb - t).total_seconds() for tb, db in B
                   if 0 < (tb - t).total_seconds() <= WIN and db * delta > 0]
            if fol:
                lead[tag] += 1; lags[tag].append(min(fol))
            else:
                lead[tag + " (no follow)"] += 1
    if i % 2000 == 0: print(f"  ..{i}/{len(keys)} keys, {nkeys} usable", flush=True)

print(f"\nusable keys (both books with >=1 price change): {nkeys}\n")
print("=== DOES A MOVE IN ONE BOOK GET FOLLOWED BY THE OTHER (same direction, <=1h)? ===")
for tag in ("fd->dk", "dk->fd"):
    f = lead[tag]; nf = lead[tag + " (no follow)"]; tot = f + nf
    if tot:
        L = lags[tag]
        print(f"  {tag}: {f}/{tot} moves followed ({f/tot*100:5.1f}%)   "
              f"median lag {st.median(L)/60:6.1f} min" if L else f"  {tag}: none")
a = lead["fd->dk"]; an = lead["fd->dk (no follow)"]
b = lead["dk->fd"]; bn = lead["dk->fd (no follow)"]
if (a+an) and (b+bn):
    pa, pb = a/(a+an), b/(b+bn)
    pp = (a+b)/(a+an+b+bn)
    se = math.sqrt(pp*(1-pp)*(1/(a+an)+1/(b+bn))) if 0 < pp < 1 else 1e-12
    print(f"\n  ASYMMETRY: fd-leads {pa*100:.1f}% vs dk-leads {pb*100:.1f}%  "
          f"gap {(pa-pb)*100:+.1f}pp  z={(pa-pb)/se:+.2f}")
    print("  (symmetric rates = both books reacting to the same news, NOT one leading the other)")
