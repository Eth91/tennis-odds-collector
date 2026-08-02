#!/usr/bin/env python3
"""⛳ Golf CLV meter (shape-agnostic, Phase-4 of PGA_PLAN.md). For every (event, market,
runner, handicap) in golf_lines.sqlite: first-captured price vs last price. Aggregates
open->close ratio by MARKET TYPE weekly -> golf_clv.json. This ranks derivative markets
by opener softness with zero parsing assumptions — the Phase-1 softness scan, live."""
import datetime as dt
import json
import sqlite3
import statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
con = sqlite3.connect(HERE / "golf_lines.sqlite")
rows = con.execute("SELECT event, market, mtype, runner, handicap, collected_at, odds "
                   "FROM golf_lines ORDER BY collected_at").fetchall()
series = defaultdict(list)
for ev, mk, mt, rn, hc, ts, od in rows:
    series[(ev, mk, mt, rn, hc)].append((ts, od))
agg = defaultdict(list)
for (ev, mk, mt, rn, hc), pts in series.items():
    if len(pts) < 2:
        continue
    first, last = pts[0][1], pts[-1][1]
    span_h = ((dt.datetime.fromisoformat(pts[-1][0]) -
               dt.datetime.fromisoformat(pts[0][0])).total_seconds() / 3600)
    if span_h < 6 or last <= 1:
        continue
    agg[mt].append(first / last)
out = {"updated": dt.datetime.utcnow().replace(microsecond=0).isoformat(), "markets": {}}
for mt, v in sorted(agg.items(), key=lambda x: -len(x[1])):
    out["markets"][mt] = {"n": len(v), "mean_open_over_close": round(st.mean(v), 4),
                          "median": round(st.median(v), 4)}
    print(f"{mt:<28} n={len(v):>5} open/close mean {st.mean(v):.3f} median {st.median(v):.3f}")
json.dump(out, open(HERE / "golf_clv.json", "w"), indent=1)
print("done")
