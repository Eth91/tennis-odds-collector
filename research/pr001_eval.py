"""PR-001 readiness + evaluation. Bar (verbatim):
  n >= 40 newly graded TRACKED bets after 2026-08-13
  high-vac hit% exceeds low-vac by >= 10pp
  two-proportion z >= 2.94 on the NEW rows alone
  total units improve vs unfiltered v1.8 on the NEW rows alone
FAILURE: gap < 5pp, or sign flip, at n >= 40.
RULE: drop a tracked bet when vac IS NOT NULL AND vac <= 14.7. NULL vac is KEPT.

Applying the PR-002 lesson: also report concentration (does removing the top winners kill it?)."""
import sqlite3, sys, statistics as st, math
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_slip as S
c = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/wnba_ledger.sqlite?mode=ro", uri=True, timeout=30)
c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute("SELECT * FROM predictions")]
overs = [r for r in rows if (r.get("side") or "over")=="over" and (r.get("tier") or "firm")!="n1"]
kept, _ = S.current_selection(overs, commit=False)
def b(r):
    res=str(r.get("result") or "").lower()
    return "VOID" if res=="void" else ("W" if res=="over" else ("L" if res=="under" else "P"))
NEW = [r for r in kept if str(r["pred_date"]) > "2026-08-13" and b(r) in ("W","L")]
print(f"newly graded tracked bets after 2026-08-13: {len(NEW)}   (bar needs >= 40)")
have = [r for r in NEW if r.get("vac") is not None]
print(f"  with vac populated: {len(have)}   vac NULL (kept by the rule): {len(NEW)-len(have)}")
if len(NEW) < 40:
    print(f"\n  NOT READY — {40-len(NEW)} more graded tracked bets needed. Not inspecting further.")
    raise SystemExit
hi = [r for r in have if float(r["vac"]) > 14.7]
lo = [r for r in have if float(r["vac"]) <= 14.7]
def hit(s): return sum(1 for r in s if b(r)=="W")/len(s)*100 if s else 0
def un(s): return sum(float(r["odds"])-1 for r in s if b(r)=="W") - sum(1 for r in s if b(r)=="L")
print(f"\n  HIGH vac (>14.7): n={len(hi)}  hit {hit(hi):.1f}%  {un(hi):+.2f}u")
print(f"  LOW  vac (<=14.7): n={len(lo)}  hit {hit(lo):.1f}%  {un(lo):+.2f}u")
gap = hit(hi) - hit(lo)
if hi and lo:
    p1, p2 = hit(hi)/100, hit(lo)/100
    pp = (sum(1 for r in hi if b(r)=="W")+sum(1 for r in lo if b(r)=="W"))/(len(hi)+len(lo))
    se = math.sqrt(pp*(1-pp)*(1/len(hi)+1/len(lo))) if 0<pp<1 else 1e-9
    z = (p1-p2)/se
else:
    z = 0
filtered = [r for r in NEW if not (r.get("vac") is not None and float(r["vac"]) <= 14.7)]
print(f"\n  UNFILTERED (v1.8) new rows: n={len(NEW)}  {un(NEW):+.2f}u")
print(f"  FILTERED (PR-001 rule):     n={len(filtered)}  {un(filtered):+.2f}u")
print("\n=== VERDICT AGAINST THE FROZEN BAR ===")
c1 = len(NEW) >= 40;                 print(f"  [{'PASS' if c1 else 'FAIL'}] n >= 40                 -> {len(NEW)}")
c2 = gap >= 10;                      print(f"  [{'PASS' if c2 else 'FAIL'}] hit gap >= 10pp         -> {gap:+.1f}pp")
c3 = z >= 2.94;                      print(f"  [{'PASS' if c3 else 'FAIL'}] z >= 2.94               -> {z:+.2f}")
c4 = un(filtered) > un(NEW);         print(f"  [{'PASS' if c4 else 'FAIL'}] units improve           -> {un(filtered):+.2f}u vs {un(NEW):+.2f}u")
fail = gap < 5
print(f"\n  FAILURE CONDITION (gap < 5pp or sign flip): {'TRIGGERED' if fail else 'not triggered'}")
print(f"  >>> {'PROMOTE' if all([c1,c2,c3,c4]) else ('REJECT' if fail else 'HOLD — bar not met, failure not triggered')}")
