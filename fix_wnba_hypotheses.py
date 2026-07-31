"""Register open hypotheses in the evidence report, so they are settled by prospective data.

The WNBA report had a standing instruction but nowhere to record WHAT is pending. Two live ones,
both surfaced 2026-07-31, and they point in OPPOSITE directions for the same pair of bets — which is
exactly why they belong in a pre-registered file rather than in an argument.
"""
import ast, io, shutil
P="wnba_validate.py"; s=io.open(P,encoding="utf-8").read()
if "Registered open hypotheses" in s:
    print("  = hypotheses section already present"); raise SystemExit(0)

old = '''    L += ["## Standing instruction", "",
          "No model change is proposed or adopted on this evidence. Every modification is a new "
          "hypothesis and must clear the adoption rule above on PROSPECTIVE data.", ""]'''
new = '''    L += ["## Standing instruction", "",
          "No model change is proposed or adopted on this evidence. Every modification is a new "
          "hypothesis and must clear the adoption rule above on PROSPECTIVE data.", "",
          "### Registered open hypotheses", "",
          "- **H-6 — should DvP carry more than TIEBREAKER weight?** `prop_edges` adds "
          "`dvp(opp,pos,stat) * proj_min` to `elev_avg` and nothing more, on the basis that the "
          "backtest looked marginal. Re-run leak-free on 954 spots (`dvp_backtest.py`), it is not "
          "marginal for the side we actually bet: OVERS into a soft positional defence went "
          "**27-12 / 69.2%**, overs into a tough one **14-17 / 45.2%** — a 24-point gap, n=70, "
          "z=2.02. MAE barely moves (2.85 to 2.84), which is how it was mistaken for marginal: it "
          "improves BET SELECTION far more than it improves the projection, and MAE cannot see "
          "that. Candidate change: gate or downweight overs where |coef| > 0.010 and the sign "
          "opposes the bet. NOT adopted — the 954 spots are the backtest's own universe, not our "
          "carded bets, so it must still clear the paired-SPRT rule prospectively.",
          "",
          "- **H-5 — the correlation cap ranking.** SHIPPED as v1.1 (A-band before odds). It "
          "changed zero past bets because no historical contest had the split-band shape, so it "
          "is untested by construction. Watch whether the play it now keeps outperforms the one "
          "it used to.",
          "",
          "  ⚠ **H-5 and H-6 disagree on the same bet.** POR 2026-07-31: DiLeo has the role "
          "expansion (+4.2 min, +3.1 FGA, tier A) but is a CENTRE into IND, our 3rd-toughest "
          "matchup vs C; Carleton has almost no role change (+0.3 min) but is a FORWARD into our "
          "2nd-SOFTEST matchup vs F. H-5 keeps DiLeo, H-6 prefers Carleton. On current evidence "
          "H-6 rests on the larger and statistically significant sample (n=70, z=2.02) while the "
          "tier gap behind H-5 is not significant (A 82.4% vs B 60.7%, n=17/28, z=1.52). Do not "
          "resolve this by argument — it is why both are registered.", ""]'''
assert old in s, "standing-instruction anchor missing"
s=s.replace(old,new,1)
ast.parse(s)
shutil.copyfile(P,"/tmp/wnba_validate.prehyp.py")
io.open(P,"w",encoding="utf-8").write(s)
print("  + H-5 and H-6 registered, with the conflict stated")
