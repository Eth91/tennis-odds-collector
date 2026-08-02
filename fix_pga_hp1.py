"""Register H-P1: within-tournament form is real, net of conditions."""
import ast, io, shutil
P="pga_validate.py"; s=io.open(P,encoding="utf-8").read()
if "H-P1" in s:
    print("  = H-P1 already registered"); raise SystemExit(0)
old = '    L += ["## Standing instruction", "",'
new = ('''    L += ["## Registered open hypotheses", "",
          "- **H-P1 — should player rates use the CURRENT tournament's completed rounds?** They do "
          "not today: `pga_birdies.rates()` reads the harvested history, refreshed WEEKLY, so this "
          "week's R1 is absent and a player who shot 65 and one who shot 77 are priced "
          "identically — while the book has fully absorbed the difference. The only channel R1 "
          "reaches the model is the FIELD-level LAM anchor.",
          "",
          "  Tested 2026-07-31 on 42,557 harvested player-rounds across 114 events. Conditions "
          "removed first at the round level (field rate that round / field rate that event), "
          "because a course plays harder or easier round to round and that would otherwise "
          "masquerade as form — the factors do range 0.88x to 1.13x. Player baselines are "
          "LEAVE-ONE-EVENT-OUT so the current tournament never informs its own expectation.",
          "",
          "  Residual carry-over: **R1→R2 +0.150 (n=12,593), R2→R3 +0.156 (n=7,757), "
          "R3→R4 +0.156 (n=7,406)**, pooled **+0.152 on 27,756 pairs**, against a shuffled "
          "cross-event null of **-0.005**. Three independent round-pairs within 0.006 of each "
          "other and a clean null: the effect is real.",
          "",
          "  Worth: residual sd is 1.79 birdies per 18, so r=0.152 moves the next round's "
          "projection ~**0.27 birdies**. This week's flags sit 0.5-1.0 birdies from their lines, so "
          "it would move some across but is not decisive.",
          "",
          "  ⚠ **Predicting the rate is not the same as making money.** The book almost certainly "
          "prices R1 form already, so adding it should REDUCE flags rather than fatten edges — it "
          "removes a reason we disagree with the market wrongly. That is still the right direction: "
          "the forensic verdict on this model was that a LOW-INFORMATION model compressed toward "
          "the base rate and its distance from the market read as edge. The cure for that is more "
          "information, not a different threshold. NOT ADOPTED — must clear the paired-SPRT rule on "
          "prospective data.", "",
          "## Standing instruction", "",''')
assert old in s, "anchor missing"
s=s.replace(old,new,1)
ast.parse(s)
shutil.copyfile(P,"/tmp/pga_validate.prehp1.py")
io.open(P,"w",encoding="utf-8").write(s)
print("  + H-P1 registered")
