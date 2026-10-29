"""EXP-035  TASK 1: is PR-004 EXECUTABLE?  and  TASK 2: do PRE-MARKET flags carry information
independent of the eventual opening price?

TASK 1 -- the only economic question that matters. PR-004 says flagged rungs DRIFT toward the
over after opening. Drift is not profit (EXP-018: movement predicted CLV at z=5.47 and bet
outcome at z=0.57 with a sign flip). A prop cannot be sold back, so the drift is only harvestable
as a BETTER ENTRY PRICE on a bet held to settlement. So: same selections, entry at OPEN vs entry
at CLOSE, both graded on the real result.

TASK 2 -- the opening price IS the market's probability estimate. "Independent information" means:
within bins of OPENING IMPLIED PROBABILITY, do flagged rungs hit the over more than non-flagged
rungs at the same price? If yes, the flag knows something the opener does not.
⚠️ The opener includes vig, so implied prob is biased HIGH for both groups. Comparing flagged vs
non-flagged AT THE SAME opener makes the vig cancel -- which is why this is done conditionally
and never against a raw 50% line."""
import sqlite3, statistics as st, math
db = sqlite3.connect("file:research/rungs.sqlite?mode=ro", uri=True, timeout=120)
db.row_factory = sqlite3.Row
R = [dict(r) for r in db.execute("SELECT * FROM rungs WHERE won IS NOT NULL")]
print(f"graded rungs: {len(R)}   flagged {sum(r['flagged'] for r in R)}   "
      f"pre-market {sum(r['pre_market'] for r in R)}\n")

def roi(rows, price_col):
    """units per 1u staked, at the given entry price"""
    if not rows: return None, None, 0
    u = [ (r[price_col] - 1.0) if r["won"] else -1.0 for r in rows if r[price_col] and r[price_col] > 1 ]
    if not u: return None, None, 0
    return sum(u), sum(u)/len(u)*100, len(u)

print("=== TASK 1 — ENTRY AT OPEN vs ENTRY AT CLOSE (same selections, real outcomes) ===")
for lab, sel in (("ALL flagged", [r for r in R if r["flagged"]]),
                 ("PRE-MARKET flagged", [r for r in R if r["pre_market"]]),
                 ("flagged, line existed first", [r for r in R if r["flagged"] and not r["pre_market"]])):
    if len(sel) < 20: print(f"  {lab:30s} thin (n={len(sel)})"); continue
    uo, ro_, no = roi(sel, "open_dec"); uc, rc, nc = roi(sel, "close_dec")
    hit = sum(r["won"] for r in sel)/len(sel)*100
    print(f"  {lab:30s} n={len(sel):3d}  hit {hit:5.1f}%")
    print(f"      entry at OPEN   {uo:+7.2f}u   ROI {ro_:+6.1f}%   mean price {st.mean([r['open_dec'] for r in sel]):.3f}")
    print(f"      entry at CLOSE  {uc:+7.2f}u   ROI {rc:+6.1f}%   mean price {st.mean([r['close_dec'] for r in sel]):.3f}")
    print(f"      EDGE FROM ENTERING EARLY: {ro_-rc:+.1f}pp ROI, {uo-uc:+.2f}u")

print("\n=== TASK 2 — DOES THE FLAG BEAT THE OPENER? (conditional on opening implied prob) ===")
ops = sorted(r["open_p"] for r in R)
cuts = [ops[len(ops)*i//5] for i in range(1, 5)]
print(f"{'opener bin':>18s} {'flagged':>22s} {'non-flagged':>22s} {'gap':>9s} {'z':>7s}")
tot_z = []
for i in range(5):
    lo = cuts[i-1] if i else -1; hi = cuts[i] if i < 4 else 2
    f = [r for r in R if r["flagged"] and lo < r["open_p"] <= hi]
    n = [r for r in R if not r["flagged"] and lo < r["open_p"] <= hi]
    if len(f) < 15 or len(n) < 30:
        print(f"{f'<= {hi:.3f}':>18s}   thin (flagged n={len(f)})"); continue
    pf = sum(x["won"] for x in f)/len(f); pn = sum(x["won"] for x in n)/len(n)
    pp = (sum(x["won"] for x in f)+sum(x["won"] for x in n))/(len(f)+len(n))
    se = math.sqrt(pp*(1-pp)*(1/len(f)+1/len(n))) if 0 < pp < 1 else 1e-12
    z = (pf-pn)/se; tot_z.append(z)
    print(f"{f'<= {hi:.3f}':>18s} {pf*100:8.1f}% (n={len(f):3d}) {pn*100:12.1f}% (n={len(n):4d}) "
          f"{(pf-pn)*100:+8.1f}pp {z:+7.2f}")
print("\n  same, restricted to the PRE-MARKET cohort (flagged BEFORE the line opened):")
for i in range(5):
    lo = cuts[i-1] if i else -1; hi = cuts[i] if i < 4 else 2
    f = [r for r in R if r["pre_market"] and lo < r["open_p"] <= hi]
    n = [r for r in R if not r["flagged"] and lo < r["open_p"] <= hi]
    if len(f) < 12 or len(n) < 30: continue
    pf = sum(x["won"] for x in f)/len(f); pn = sum(x["won"] for x in n)/len(n)
    pp = (sum(x["won"] for x in f)+sum(x["won"] for x in n))/(len(f)+len(n))
    se = math.sqrt(pp*(1-pp)*(1/len(f)+1/len(n))) if 0 < pp < 1 else 1e-12
    print(f"{f'<= {hi:.3f}':>18s} {pf*100:8.1f}% (n={len(f):3d}) {pn*100:12.1f}% (n={len(n):4d}) "
          f"{(pf-pn)*100:+8.1f}pp {(pf-pn)/se:+7.2f}")

print("\n=== TASK 2b — CALIBRATION: does the OPENER already price the flag correctly? ===")
print("  (actual over-rate minus opener-implied prob; ~-4pp is normal vig on a fair line)")
for lab, sel in (("flagged", [r for r in R if r["flagged"]]),
                 ("pre-market flagged", [r for r in R if r["pre_market"]]),
                 ("non-flagged", [r for r in R if not r["flagged"]])):
    if len(sel) < 20: continue
    d = [r["won"] - r["open_p"] for r in sel]
    se = st.pstdev(d)/math.sqrt(len(d)) or 1e-12
    print(f"  {lab:22s} n={len(sel):5d}  actual-minus-implied {st.mean(d)*100:+6.2f}pp  "
          f"t={st.mean(d)/se:+6.2f}")
