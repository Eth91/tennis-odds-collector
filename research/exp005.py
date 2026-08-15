"""EXP-005 TEMPORAL SPLIT of the EXP-004 candidates.
EXP-004 found proj_min/vac/total using ALL data, so it is exposed to multiple testing.
Honest test: fit direction on PRE-FREEZE only, then check it holds on FORWARD only.
A candidate that flips sign, or ranks only in the pooled cut, is an artifact."""
import sys, os, sqlite3, statistics as st
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wnba_slip as S
FWD = "2026-07-31"
con = sqlite3.connect("file:wnba_ledger.sqlite?mode=ro", uri=True, timeout=30)
con.row_factory = sqlite3.Row
rows = [dict(r) for r in con.execute("SELECT * FROM predictions")]
keep, _ = S.current_selection(rows)
g = [r for r in keep if r["result"] in ("over", "under")]
won = lambda r: 1 if r["result"] == (r["side"] or "over") else 0
pre = [r for r in g if r["pred_date"] < FWD]
fwd = [r for r in g if r["pred_date"] >= FWD]
print(f"pre-freeze n={len(pre)}  forward n={len(fwd)}\n")

def med_split(rs, f):
    v = [(float(r[f]), won(r), float(r["odds"])) for r in rs if r.get(f) is not None]
    if len(v) < 8: return None
    m = st.median([x[0] for x in v])
    lo = [x for x in v if x[0] <= m]; hi = [x for x in v if x[0] > m]
    if not lo or not hi: return None
    def rec(s):
        w = sum(x[1] for x in s); u = sum((x[2]-1) if x[1] else -1 for x in s)
        return len(s), w/len(s)*100, u/len(s)*100
    return m, rec(lo), rec(hi)

print(f"{'field':10s} {'cut':4s} {'median':>7s} {'LOW half':>22s} {'HIGH half':>22s}  verdict")
print("-"*88)
for f in ("proj_min", "vac", "total"):
    res = {}
    for lbl, rs in (("pre", pre), ("fwd", fwd)):
        r = med_split(rs, f)
        if not r: 
            print(f"{f:10s} {lbl:4s}  insufficient"); continue
        m,(nl,hl,rl),(nh,hh,rh) = r
        res[lbl] = hh-hl
        print(f"{f:10s} {lbl:4s} {m:7.1f}  n={nl:2d} {hl:5.1f}% ROI{rl:+6.1f}%   "
              f"n={nh:2d} {hh:5.1f}% ROI{rh:+6.1f}%")
    if "pre" in res and "fwd" in res:
        same = (res["pre"]>0) == (res["fwd"]>0)
        print(f"{'':10s}      HIGH-minus-LOW hit%: pre {res['pre']:+.1f}pp, fwd {res['fwd']:+.1f}pp"
              f"  -> {'SAME direction (holds)' if same else 'SIGN FLIP (artifact)'}\n")
