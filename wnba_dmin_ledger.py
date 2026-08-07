#!/usr/bin/env python3
"""Restate the tracked record with a minutes-bump cap — on the LIVE ledger.

The replay could not test this: 124 candidates with an 8+ bump enter it and none survive to
become a graded bet, while the live model bets that band 17 times in 183. So the gate is
tested here instead, on the actual population it would act on.

The cap is applied BEFORE current_selection, so dropping a play frees its TOP-2 slot for the
next-best one — the same promotion a live gate would cause. Filtering afterwards would leave a
hole and understate the change.
"""
import sqlite3, statistics as st, sys
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_slip as S

L = "/home/ubuntu/wnba_data/wnba_ledger.sqlite"
c = sqlite3.connect(f"file:{L}?mode=ro", uri=True)
c.row_factory = sqlite3.Row
allrows = [dict(r) for r in c.execute("SELECT * FROM predictions")]
c.close()


def score(rows):
    w = l = v = 0
    u = 0.0
    for r in rows:
        res = r.get("result") or ""
        if not res:
            continue
        side = r.get("side") or "over"
        od = r.get("odds") or 0
        if res == "void":
            v += 1
            continue
        if res == side:
            w += 1; u += (od - 1.0)
        else:
            l += 1; u -= 1.0
    return w, l, v, round(u, 2)


print(f"{'cap':<14}{'record':>12}{'hit':>8}{'units':>9}{'vs base':>10}{'bets cut':>10}")
base_u = None
base_n = None
for cap in (None, 12.0, 10.0, 8.0, 6.0, 5.0):
    if cap is None:
        pool = allrows
        label = "shipped"
    else:
        pool = [r for r in allrows
                if r.get("d_min") is None or float(r["d_min"]) <= cap]
        label = f"d_min<={cap:g}"
    kept, _ = S.current_selection(pool)
    w, l, v, u = score(kept)
    if base_u is None:
        base_u, base_n = u, w + l
    hit = 100.0 * w / max(w + l, 1)
    print(f"{label:<14}{f'{w}-{l}':>12}{hit:>7.1f}%{u:>+9.2f}{u-base_u:>+10.2f}"
          f"{base_n-(w+l):>10}")

print("\nthe bets a cap removes (d_min > 8), as the tracker scores them:")
big = [r for r in allrows if r.get("d_min") is not None and float(r["d_min"]) > 8]
kb, _ = S.current_selection(big)
w, l, v, u = score(kb)
print(f"  d_min>8 inside the tracked selection: {w}-{l} ({v} void)  {u:+.2f}u")
for r in sorted(kb, key=lambda x: -(x.get("d_min") or 0))[:10]:
    res = r.get("result") or "-"
    side = r.get("side") or "over"
    tag = "VOID" if res == "void" else ("WIN " if res == side else "loss")
    print(f"    {tag} {r.get('pred_date')} {r.get('player'):<22} {r.get('stat'):<8} "
          f"{side} {r.get('line')}  d_min {r.get('d_min')}")
