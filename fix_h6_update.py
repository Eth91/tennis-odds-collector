"""Record the first test of H-6 against our OWN carded bets. It does not transfer."""
import ast, io, shutil
P="wnba_validate.py"; s=io.open(P,encoding="utf-8").read()
if "FIRST TEST ON OUR OWN BETS" in s:
    print("  = H-6 result already recorded"); raise SystemExit(0)
old = ('"carded bets, so it must still clear the paired-SPRT rule prospectively.",')
new = ('"carded bets, so it must still clear the paired-SPRT rule prospectively.",\n'
       '          "",\n'
       '          "  **FIRST TEST ON OUR OWN BETS (2026-07-31) — it does NOT transfer.** Refitting '
       'DvP as-of each bet\'s own date and applying the filter to the counted record makes it worse '
       'at EVERY threshold: drop coef<=-0.005 -> 20-14 / +4.53u (-14 bets, -14.52u); <=-0.010 -> '
       '29-15 / +13.43u (-5.62u); <=-0.015 -> -4.54u; <=-0.020 -> -1.26u, against a 33-15 / +19.05u '
       'baseline. The split is REVERSED here: our overs into a TOUGH positional defence went 4-0 '
       '(+5.62u) where the backtest\'s universe gave 45.2%. Plausible mechanism: the backtest scores '
       'general props, while our bets are injury-beneficiary overs whose minutes and usage are '
       'exploding — role expansion dominates matchup, so a tough defence costs far less than it '
       'does for an ordinary prop. ⚠ n=4 in that bucket proves nothing on its own; it merely fails '
       'to confirm. Also 17 of 48 bets could not be resolved to a position/opponent and went 9-8 '
       '(52.9%), worse than the resolved ones — worth its own look. CONCLUSION: do not gate on DvP; '
       'keep it as the tiebreaker it is, and let the prospective record settle it.",')
assert old in s, "H-6 anchor missing"
assert s.count(old)==1, "ambiguous anchor"
s=s.replace(old,new,1)
ast.parse(s)
shutil.copyfile(P,"/tmp/wnba_validate.preh6.py")
io.open(P,"w",encoding="utf-8").write(s)
print("  + H-6 updated with the first negative test on our own bets")
