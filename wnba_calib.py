#!/usr/bin/env python3
"""Why are we not gaining units? First question: is the model's own confidence predictive?

If a +40% EV flag does not beat a +11% EV flag, the ranking is noise — and every gate built on
it (TOP-2, tier ordering, swap rules) is sorting randomly. That would explain flat results far
better than any single filter would.

Buckets every graded ledger row by the model's ev and proj_hit, and compares the PREDICTED win
rate to the REALISED one. Runs on all rows and on the tracked selection separately.
"""
import sqlite3, statistics as st, sys
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_slip as S

L = "/home/ubuntu/wnba_data/wnba_ledger.sqlite"
c = sqlite3.connect(f"file:{L}?mode=ro", uri=True)
c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute(
    "SELECT * FROM predictions WHERE result IS NOT NULL AND result<>'' AND result<>'void'")]
kept, _ = S.current_selection(rows)


def graded(rs):
    out = []
    for r in rs:
        side = r.get("side") or "over"
        res = r.get("result") or ""
        od = r.get("odds") or 0
        if not od:
            continue
        out.append({"win": 1 if res == side else 0, "ev": r.get("ev"),
                    "ph": r.get("proj_hit"), "odds": od,
                    "dmin": r.get("d_min"), "n": r.get("n_elev")})
    return out


def bucket(rs, field, edges, label):
    print(f"\n  -- {label} --")
    for lo, hi in zip(edges, edges[1:]):
        sel = [x for x in rs if x[field] is not None and lo <= x[field] < hi]
        if len(sel) < 8:
            print(f"    {lo:>5.2f}-{hi:<5.2f} n={len(sel):<4} (thin)")
            continue
        w = sum(x["win"] for x in sel)
        hit = w / len(sel)
        be = st.mean([1.0 / x["odds"] for x in sel])
        u = sum((x["odds"] - 1.0) if x["win"] else -1.0 for x in sel)
        pred = st.mean([x["ph"] for x in sel if x["ph"] is not None] or [float("nan")])
        print(f"    {lo:>5.2f}-{hi:<5.2f} n={len(sel):<4} {w}-{len(sel)-w}  "
              f"hit {100*hit:5.1f}%  predicted {100*pred:5.1f}%  "
              f"be {100*be:5.1f}%  edge {100*(hit-be):+6.1f}  {u:+7.2f}u")


for name, rs in (("ALL GRADED", graded(rows)), ("TRACKED SELECTION", graded(kept))):
    print(f"\n{'='*74}\n{name}  (n={len(rs)})\n{'='*74}")
    if len(rs) < 20:
        print("  too few to bucket")
        continue
    w = sum(x["win"] for x in rs)
    be = st.mean([1.0 / x["odds"] for x in rs])
    print(f"  overall {w}-{len(rs)-w}  hit {100*w/len(rs):.1f}%  breakeven {100*be:.1f}%")
    bucket(rs, "ev", [0.0, 0.10, 0.15, 0.25, 0.40, 9.0], "by model EV")
    bucket(rs, "ph", [0.0, 0.55, 0.65, 0.75, 0.85, 1.01], "by projected hit rate")
    bucket(rs, "dmin", [-99, 1, 3, 8, 99], "by minutes bump")
    bucket(rs, "n", [0, 5, 8, 12, 999], "by elevated-sample size")
