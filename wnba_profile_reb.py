#!/usr/bin/env python3
"""Profile the rebound bets — hunt BUGS freely, treat PATTERNS with suspicion.

With 55 bets, any search for what separates wins from losses will find something. So every
feature split is reported PER SEASON: a pattern that only appears in one is noise, and only one
that holds independently in both is worth anything. Bugs are different — an implausible line, a
duplicate, a mismatched player is wrong regardless of sample size.
"""
import sys, statistics as st
from collections import defaultdict, Counter
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
sys.path.insert(0, "/home/ubuntu")
import wnba_funnel_stint as F

CFG = dict(samepos=True, min_apart=0.0, starter=0.0, max_nwo=8, ev_bar=0.10, top_n=2)
b26 = [dict(b, season=2026) for b in F.run_cfg(2026, "rebounds", **CFG)]
b25 = [dict(b, season=2025) for b in F.run_cfg(2025, "rebounds", **CFG)]
allb = b26 + b25

print("=== EVERY BET ===")
for b in sorted(allb, key=lambda x: (x["season"], x["date"])):
    print(f"  {'WIN ' if b['hit'] else 'loss'} {b['date']} {b['player']:<22} "
          f"w/o {b['out']:<20} line {b['line']:<5g} @{b['dec']:.2f} "
          f"ev {b['ev']*100:+5.1f}% shift {b['shift']:.2f} n={b['n']}")

print("\n=== BUG CHECKS ===")
dupes = [k for k, v in Counter((b["date"], b["player"], b["line"]) for b in allb).items() if v > 1]
print(f"  duplicate (date,player,line) rows: {len(dupes)} {dupes[:3]}")
odd = [b for b in allb if b["dec"] < 1.2 or b["dec"] > 6.0]
print(f"  implausible prices (<1.20 or >6.00): {len(odd)}")
badline = [b for b in allb if b["line"] < 1.5 or b["line"] > 15.5]
print(f"  implausible rebound lines (<1.5 or >15.5): {len(badline)}")
hishift = [b for b in allb if b["shift"] > 2.0]
print(f"  usage shift >2.0x (suspicious rate): {len(hishift)}"
      + (f"  e.g. {hishift[0]['player']} {hishift[0]['shift']:.2f}" if hishift else ""))
thin = [b for b in allb if b["n"] < 8]
print(f"  built on <8 prior games: {len(thin)}")
samep = [b for b in allb if b["player"] == b["out"]]
print(f"  player == out player (should be 0): {len(samep)}")


def split(field, buckets, label):
    print(f"\n  -- {label} --")
    print(f"    {'bucket':<16}{'2026':>16}{'2025':>16}{'both':>16}")
    for lo, hi in zip(buckets, buckets[1:]):
        row = []
        for rs in (b26, b25, allb):
            sel = [b for b in rs if lo <= b[field] < hi]
            if len(sel) < 4:
                row.append(f"n={len(sel)}")
                continue
            w = sum(b["hit"] for b in sel)
            row.append(f"{w}-{len(sel)-w} {100*w/len(sel):.0f}%")
        print(f"    {lo:<6g}-{hi:<8g}{row[0]:>16}{row[1]:>16}{row[2]:>16}")


print("\n=== PATTERNS (per season — only trust what repeats) ===")
split("ev", [0.10, 0.20, 0.35, 0.60, 9.0], "by model EV")
split("shift", [1.0, 1.15, 1.35, 1.6, 9.0], "by usage shift (apart rate / overall)")
split("line", [1.5, 4.5, 6.5, 8.5, 20.0], "by posted line")
split("dec", [1.0, 1.75, 1.95, 2.3, 9.0], "by price")
split("n", [0, 10, 18, 26, 999], "by prior games used")

print("\n=== who repeats ===")
for tag, rs in (("2026", b26), ("2025", b25)):
    c = Counter(b["player"] for b in rs)
    w = defaultdict(int)
    for b in rs:
        w[b["player"]] += b["hit"]
    top = c.most_common(5)
    print(f"  {tag}: " + ", ".join(f"{p.split()[-1]} {w[p]}-{n-w[p]}" for p, n in top))
