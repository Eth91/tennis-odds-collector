#!/usr/bin/env python3
"""Which filter is costing the volume — and does the edge survive relaxing it?

31 rebound bets across two seasons is one every ~10 days. Before accepting that as the real
size of the spot, find out where the candidates die and whether the expensive filters are
earning their keep. Two parts:

  FUNNEL   how many candidates survive each stage, in order
  RELAX    re-run with ONE filter loosened at a time, both seasons, edge reported

A filter is worth keeping only if dropping it BOTH adds volume and costs edge. If dropping it
adds volume and keeps the edge, it was never doing anything but shrinking the sample.
"""
import sys, sqlite3, statistics as st
from collections import defaultdict, Counter

sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
sys.path.insert(0, "/home/ubuntu")
import wnba_stint_proper as P
import wnba_wowy as W

FUNNEL = Counter()


def run_cfg(season, stat, *, samepos=True, min_apart=50.0, starter=25.0,
            max_nwo=2, ev_bar=0.10, top_n=2, count_funnel=False):
    """Same pipeline as wnba_stint_proper.run but with each filter parameterised."""
    P.MIN_APART, P.STARTER_MIN, P.MAX_NWO = min_apart, starter, max_nwo
    P.EV_BAR, P.TOP_N = ev_bar, top_n
    P.SAMEPOS = samepos
    bets, skipped = P.run(season, stat)
    return bets


def summ(bets):
    if not bets:
        return "0 bets"
    w = sum(b["hit"] for b in bets); l = len(bets) - w
    u = sum((b["dec"] - 1.0) if b["hit"] else -1.0 for b in bets)
    be = st.mean([1.0 / b["dec"] for b in bets])
    hit = w / len(bets)
    return (f"{w}-{l}  hit {100*hit:5.1f}%  edge {100*(hit-be):+6.1f}  {u:+7.2f}u")


if __name__ == "__main__":
    stat = sys.argv[1] if len(sys.argv) > 1 else "rebounds"
    base = dict(samepos=True, min_apart=50.0, starter=25.0, max_nwo=2, ev_bar=0.10, top_n=2)
    variants = [
        ("BASE (as tested)",        {}),
        ("no same-position",        {"samepos": False}),
        ("apart >=25min",           {"min_apart": 25.0}),
        ("apart >=10min",           {"min_apart": 10.0}),
        ("apart: no minimum",       {"min_apart": 0.0}),
        ("starters >=20min",        {"starter": 20.0}),
        ("no starter filter",       {"starter": 0.0}),
        ("n_without <=4",           {"max_nwo": 4}),
        ("n_without <=8 (all)",     {"max_nwo": 8}),
        ("TOP-3 per game",          {"top_n": 3}),
        ("no same-pos + apart>=25", {"samepos": False, "min_apart": 25.0}),
    ]
    print(f"=== {stat.upper()} — one filter relaxed at a time ===\n")
    print(f"{'variant':<26}{'2026':>34}{'2025':>34}")
    for label, over in variants:
        cfg = dict(base); cfg.update(over)
        try:
            b26 = run_cfg(2026, stat, **cfg)
            b25 = run_cfg(2025, stat, **cfg)
        except Exception as e:
            print(f"{label:<26} ERROR {type(e).__name__}: {str(e)[:40]}")
            continue
        print(f"{label:<26}{summ(b26):>34}{summ(b25):>34}")
    print("\nKeep a filter only if relaxing it costs EDGE. If relaxing it adds volume and holds")
    print("the edge, the filter was only shrinking the sample.")
