"""WHY did `elevated` candidates collapse 116 -> 33? Volume is the binding constraint on total
units (1.67 bets/day vs 3.80 pre-freeze), and volume is a LEGITIMATE lever: it changes how many
candidates clear the gate, not which ones win, so investigating it cannot contaminate the
forward hit rate.

Injuries explain only -29% (out-players 1.50 -> 1.06/day). The other ~43% is something else."""
import sqlite3, sys, statistics as st
from collections import Counter, defaultdict
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
c = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/wnba_ledger.sqlite?mode=ro", uri=True, timeout=30)
c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute("SELECT * FROM predictions")]
PRE = lambda r: str(r["pred_date"]) < "2026-07-31"
for lab, f in (("PRE-FREEZE", PRE), ("FORWARD", lambda r: not PRE(r))):
    s = [r for r in rows if f(r)]
    d = len({str(r["pred_date"]) for r in s})
    el = [r for r in s if str(r.get("basis")) == "elevated"]
    print(f"\n{lab}: {d} slate-days, {len(s)} raw rows ({len(s)/d:.2f}/day)")
    print(f"  elevated rows: {len(el)} ({len(el)/d:.2f}/day)")
    for fld in ("n_elev", "d_min", "proj_min", "vac", "ev"):
        v = [float(r[fld]) for r in el if r.get(fld) is not None]
        if v: print(f"    {fld:9s} median {st.median(v):6.2f}  mean {st.mean(v):6.2f}  min {min(v):6.2f}")
    print(f"    distinct beneficiaries {len({r['player'] for r in el})}  "
          f"distinct out_players {len({str(r.get('out_player')) for r in el})}")
print("\n=== is the season simply winding down? raw rows + slates per week ===")
byw = defaultdict(lambda: [0, set()])
for r in rows:
    d = str(r["pred_date"])
    wk = d[:7] + "-w" + str((int(d[8:10]) - 1)//7 + 1)
    byw[wk][0] += 1; byw[wk][1].add(d)
for wk in sorted(byw):
    n, ds = byw[wk]
    print(f"  {wk}  {n:4d} rows over {len(ds):2d} slates = {n/len(ds):5.2f}/slate")
print("\n=== elevated-sample gate: what n_elev do candidates carry over time? ===")
for wk in sorted(byw):
    s = [r for r in rows if (str(r['pred_date'])[:7] + "-w" + str((int(str(r['pred_date'])[8:10])-1)//7+1)) == wk
         and str(r.get("basis")) == "elevated" and r.get("n_elev") is not None]
    if len(s) >= 4:
        v = [float(r["n_elev"]) for r in s]
        print(f"  {wk}  n={len(s):3d}  n_elev median {st.median(v):5.1f}  min {min(v):4.1f}")
