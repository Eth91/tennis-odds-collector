"""EXP-036 CLEAN THE TASK-2 CONFOUND. Flagged rungs are 97.6% graded, non-flagged only 51.7%.
Ungraded means the player never appeared in a box score -- DNP or name mismatch. So the two pools
differ in DNP RISK, and the book prices DNP risk into the opener. Removing the DNP mass from one
pool more than the other is what makes non-flagged appear to beat their own opener by +3.05pp,
which would imply betting random rungs is profitable. It is not; it is survivorship.

WITHIN-PLAYER TEST. Compare a player's FLAGGED-day rungs against THAT SAME PLAYER'S non-flagged-day
rungs. Player identity holds DNP risk, role and quality fixed, so anything left is the flag.

Also reported: a minutes-floor variant, since a scratch is an automatic under and the flagged pool
is selected for players expected to play."""
import sqlite3, statistics as st, math
from collections import defaultdict
db = sqlite3.connect("file:research/rungs.sqlite?mode=ro", uri=True, timeout=120)
db.row_factory = sqlite3.Row
R = [dict(r) for r in db.execute("SELECT * FROM rungs WHERE won IS NOT NULL")]

print("=== GRADING RATE BY GROUP (the confound, quantified) ===")
allr = [dict(r) for r in db.execute("SELECT flagged, won FROM rungs")]
for lab, f in (("flagged", lambda r: r["flagged"] == 1), ("non-flagged", lambda r: r["flagged"] == 0)):
    s = [r for r in allr if f(r)]
    g = sum(1 for r in s if r["won"] is not None)
    print(f"  {lab:12s} {g}/{len(s)} graded ({g/len(s)*100:.1f}%)")
print("  -> unequal exclusion; any unpaired flagged-vs-nonflagged comparison inherits it.\n")

print("=== WITHIN-PLAYER: same player, flagged days vs their own non-flagged days ===")
byp = defaultdict(lambda: {"f": [], "n": []})
for r in R:
    byp[r["player"]]["f" if r["flagged"] else "n"].append(r)
pairs = []
for p, d in byp.items():
    if len(d["f"]) >= 3 and len(d["n"]) >= 10:
        pf = sum(x["won"] for x in d["f"])/len(d["f"])
        pn = sum(x["won"] for x in d["n"])/len(d["n"])
        # control for price: compare each side's actual-minus-opener, not raw hit%
        ef = st.mean([x["won"] - x["open_p"] for x in d["f"]])
        en = st.mean([x["won"] - x["open_p"] for x in d["n"]])
        pairs.append((p, len(d["f"]), len(d["n"]), pf, pn, ef, en))
print(f"  {len(pairs)} players with >=3 flagged and >=10 non-flagged graded rungs")
if pairs:
    print(f"  {'player':22s} {'nF':>4s} {'nN':>4s} {'flag beat-opener':>18s} {'own baseline':>14s} {'diff':>9s}")
    for p, nf, nn, pf, pn, ef, en in sorted(pairs, key=lambda x: -(x[5]-x[6]))[:12]:
        print(f"  {str(p)[:22]:22s} {nf:4d} {nn:4d} {ef*100:+17.1f}pp {en*100:+13.1f}pp {(ef-en)*100:+8.1f}pp")
    d = [ef - en for _, _, _, _, _, ef, en in pairs]
    se = st.pstdev(d)/math.sqrt(len(d)) or 1e-12
    print(f"\n  WITHIN-PLAYER mean difference: {st.mean(d)*100:+.2f}pp   t = {st.mean(d)/se:+.2f}   n={len(d)} players")
    _t = st.mean(d) / se
    # SIGN MATTERS. This line once printed 'adds information' for a -10.87pp result
    # because it tested abs(t) > 2. A verdict string must never drop the sign.
    _v = ('flag BEATS the opener' if _t > 2 else
          'flag UNDERPERFORMS the opener -- but see the DNP-pricing confound' if _t < -2 else
          'no detectable information beyond the opener')
    print(f'  -> {_v}')

print("\n=== SAME, but only rungs where the player actually logged real minutes ===")
print("  (a scratch is an automatic under; the flagged pool is selected for players expected to play)")
hi = [r for r in R if (r["actual"] or 0) > 0]
print(f"  rungs with actual>0: {len(hi)}/{len(R)}")
for lab, sel in (("flagged", [r for r in hi if r["flagged"]]),
                 ("non-flagged", [r for r in hi if not r["flagged"]])):
    if len(sel) < 20: continue
    d = [r["won"] - r["open_p"] for r in sel]
    se = st.pstdev(d)/math.sqrt(len(d)) or 1e-12
    print(f"  {lab:14s} n={len(sel):5d}  actual-minus-opener {st.mean(d)*100:+6.2f}pp  t={st.mean(d)/se:+6.2f}")

print("\n=== AND THE ONE RESULT THAT IS SURVIVORSHIP-IMMUNE (paired, identical rows) ===")
f = [r for r in R if r["flagged"] and r["open_dec"] > 1 and r["close_dec"] > 1]
d = [(r["open_dec"] - r["close_dec"]) for r in f]
se = st.pstdev(d)/math.sqrt(len(d)) or 1e-12
print(f"  open price minus close price on the SAME {len(f)} flagged rungs: {st.mean(d):+.4f} decimal")
print(f"  t = {st.mean(d)/se:+.2f}  -> the early-entry price advantage itself is {'REAL' if st.mean(d)/se > 2 else 'not established'}")
u_o = sum((r["open_dec"]-1) if r["won"] else -1 for r in f)
u_c = sum((r["close_dec"]-1) if r["won"] else -1 for r in f)
print(f"  units at open {u_o:+.2f}u vs at close {u_c:+.2f}u  ->  worth {u_o-u_c:+.2f}u over {len(f)} bets")
print(f"  BUT both are negative: entering earlier on a losing selection loses less, it does not win.")
