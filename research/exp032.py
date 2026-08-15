"""EXP-032 §40 AUDIT of EXP-031's z=-12.50. Three specific ways that number could be an artifact:

1. SAMPLING DENSITY. fd has 2.16M observations, dk 1.10M. If fd is polled ~2x more often, then
   "fd follows dk" is mechanically EASIER to detect than "dk follows fd" -- more fd points land in
   any window. That alone could manufacture the entire 2.8pp gap.
2. NO DIRECTIONAL BASELINE. A 42% same-direction follow rate means nothing without the
   OPPOSITE-direction rate. If opposite ~= same, the books are just churning and there is no
   information flow at all.
3. EFFECT SIZE vs SAMPLE SIZE. 2.8pp on n~100k gives a huge z. Symmetric rates are the signature
   of two books reacting to the SAME news, not one leading the other."""
import sqlite3, datetime as dt, statistics as st, math
from collections import Counter, defaultdict
tick = sqlite3.connect("file:research/tick_archive.sqlite?mode=ro", uri=True, timeout=900)
days = [r[0] for r in tick.execute("SELECT DISTINCT d FROM obs ORDER BY d")]
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

dens = {"fd": [], "dk": []}
same = Counter(); opp = Counter(); nkeys = 0
for d in days:
    grp = defaultdict(lambda: {"fd": [], "dk": []})
    for player, stat, line, side, book, ca, odds in tick.execute(
            "SELECT player, stat, line, side, book, collected_at, odds FROM obs WHERE d=? "
            "ORDER BY player, stat, line, side, book, collected_at", (d,)):
        if book in ("fd", "dk"):
            grp[(player, stat, line, side)][book].append(
                (dt.datetime.fromisoformat(str(ca)), p_of(odds)))
    for key, by in grp.items():
        if len(by["fd"]) < 4 or len(by["dk"]) < 4: continue
        dens["fd"].append(len(by["fd"])); dens["dk"].append(len(by["dk"]))
        cf, cd = changes(by["fd"]), changes(by["dk"])
        if not cf or not cd: continue
        nkeys += 1
        for A, B, tag in ((cf, cd, "fd->dk"), (cd, cf, "dk->fd")):
            for t, delta in A:
                s_hit = o_hit = False
                for tb, db in B:
                    s = (tb - t).total_seconds()
                    if s <= 0: continue
                    if s > WIN: break
                    if db * delta > 0 and not s_hit: s_hit = True
                    if db * delta < 0 and not o_hit: o_hit = True
                    if s_hit and o_hit: break
                same[tag] += 1 if s_hit else 0
                opp[tag] += 1 if o_hit else 0
                same[tag + "_n"] += 1
    print(f"  {d} done, keys={nkeys}", flush=True)

print("\n=== 1. SAMPLING DENSITY per key (observations per book) ===")
for b in ("fd", "dk"):
    v = dens[b]
    print(f"  {b}: median {st.median(v):6.1f}  mean {st.mean(v):6.1f}  n_keys {len(v)}")
ratio = st.median(dens["fd"]) / max(st.median(dens["dk"]), 1e-9)
print(f"  fd/dk median density ratio: {ratio:.2f}x")
print(f"  -> {'⚠️ ASYMMETRIC SAMPLING: the lead-lag gap is confounded' if abs(ratio-1) > 0.15 else 'densities comparable'}")

print("\n=== 2. SAME- vs OPPOSITE-DIRECTION FOLLOW (the missing baseline) ===")
print(f"{'direction':>10s} {'n moves':>9s} {'same-dir':>10s} {'opp-dir':>10s} {'net':>9s}")
for tag in ("fd->dk", "dk->fd"):
    n = same[tag + "_n"]
    if not n: continue
    s, o = same[tag]/n*100, opp[tag]/n*100
    print(f"{tag:>10s} {n:9d} {s:9.1f}% {o:9.1f}% {s-o:+8.1f}pp")
print("\n  If same ~= opposite, the books are CHURNING and no information flows between them.")
net = {t: (same[t]/same[t+"_n"] - opp[t]/same[t+"_n"]) for t in ("fd->dk", "dk->fd") if same.get(t+"_n")}
if len(net) == 2:
    print(f"  net(fd->dk) {net['fd->dk']*100:+.1f}pp   net(dk->fd) {net['dk->fd']*100:+.1f}pp   "
          f"difference {(net['fd->dk']-net['dk->fd'])*100:+.1f}pp")
    print("  A real leader needs a NET-of-baseline gap, not a raw follow-rate gap.")
