# REJECTED HYPOTHESES — check before testing anything new
| id | hypothesis | result | why rejected | revisit if |
|---|---|---|---|---|
| R1 | regime-weighting (availability+arrivals+elevated) improves bets | v1.5 +15.54u vs full +10.09u on 182 rows | dropped marginal WINNERS; wowy-only alone dropped 7 bets that went 7-0 | never on ROI alone; only w/ a >+15.54u backtest |
| R2 | ~~stint-WOWY as a live bettor~~ **SUPERSEDED 2026-08-13 by PR-002** | the original verdict measured only opener(48h, 15% coverage) and T-4h(breakeven) and concluded 'edge and liquidity never overlap'. That was WRONG: 8-24h was never measured, and there coverage is 99.5-100% with ROI +14.8%..+25.2% and a NEGATIVE calibration gap | the conclusion was drawn from an unmeasured gap, not from evidence against the window | superseded — see PR-002; note the 2026-only cells are much weaker (+2.4% at 12h) |
| R3 | lower EV threshold to recover volume | 0.07/0.05 both WORSE (+8.76u vs +10.09u) | adds losers faster than winners | no |
| R4 | narrow book to alt ladders | ladders 4-4 fwd vs main 9-6 | all-time ladder edge was in-sample | no |
| R5 | USAGE_RATE_ADJ | tested, rejected pre-freeze | — | — |
| R6 | harder shrink toward book fixes the anti-predictive residual | k=0/5/11 identical; k>=20 strictly worse | shrinking removes the BET, not just the bad probability -- p_adj is both signal and gate | only with a situation-gate that does not route through p_adj |
