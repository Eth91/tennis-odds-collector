#!/usr/bin/env python3
"""POSITION-ONLY config: keep the one filter that earned its keep, drop the ones that did not.

From the sweep: same-position is essential (removing it halved the edge in BOTH seasons); the
50-minute apart bar was inert (0/10/25/50 gave identical results); the starter bar was nearly
inert; and the 0-2 games-without cap was costing real volume with no edge benefit.

The winning sweep row still carried the inert filters, so this runs the clean combination for
the first time — same-position + the model's own selection logic, nothing else — across all
three stats and both seasons.
"""
import sys, statistics as st
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
sys.path.insert(0, "/home/ubuntu")
import wnba_funnel_stint as F


def summ(bets):
    if not bets:
        return "0 bets"
    w = sum(b["hit"] for b in bets); l = len(bets) - w
    u = sum((b["dec"] - 1.0) if b["hit"] else -1.0 for b in bets)
    be = st.mean([1.0 / b["dec"] for b in bets])
    hit = w / len(bets)
    return (f"{w}-{l}  hit {100*hit:5.1f}%  be {100*be:5.1f}%  "
            f"edge {100*(hit-be):+6.1f}  {u:+7.2f}u")


CFG = dict(samepos=True, min_apart=0.0, starter=0.0, max_nwo=8, ev_bar=0.10, top_n=2)
print("POSITION-ONLY: same position + shrinkage K=11 + EV bar +10% + TOP-2 per game")
print("(no apart minimum, no starter bar, no games-without cap)\n")
for stat in ("rebounds", "assists", "points"):
    b26 = F.run_cfg(2026, stat, **CFG)
    b25 = F.run_cfg(2025, stat, **CFG)
    print(f"{stat.upper():<10} 2026  {summ(b26)}")
    print(f"{'':<10} 2025  {summ(b25)}")
    both = b26 + b25
    print(f"{'':<10} BOTH  {summ(both)}   "
          f"({len(set(b['player'] for b in both))} distinct players)")
    # de-concentration: one bet per (player, out) pair
    seen, first = set(), []
    for b in sorted(both, key=lambda x: x["date"]):
        k = (b["player"], b["out"])
        if k not in seen:
            seen.add(k); first.append(b)
    print(f"{'':<10} ONE-PER-PAIR  {summ(first)}\n")
