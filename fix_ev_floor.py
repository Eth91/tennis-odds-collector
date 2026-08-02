"""Require positive expected value explicitly. An absolute probability edge does not imply one.

THE HOLE. Both gates tested `p_bet - fair >= <threshold>` — a probability difference against the
DEVIGGED fair price. That says nothing about the vig actually paid at the offered price. Once the
top-N normaliser was corrected and the real overround became visible (21-29% on these products),
the arithmetic is unambiguous. Since `od = N_eff / (fair * inv)`:

    EV = p_bet * od - 1 = (p_bet / fair) / vig - 1

so a bet is +EV only when the BLENDED ratio beats the vig. `TN_RATIO_MIN = 1.15` sits BELOW the
1.21-1.29 vig on these markets, and `TN_EDGE = 0.02` is vig-blind, so the gate was passing bets
that cannot win. Live example from the board it was actually flagging — Nicolai Højgaard: fair
.2450, p_bet .2657, edge .0207 (clears 0.02), odds 3.20, **EV = -15.0%**. Fifteen flags, eleven of
them negative EV, mean -4.6%.

WHY 0.03 AND NOT 0. Zero is not a safe floor because the reported EV is itself a Monte Carlo
estimate. Measured directly — six independent seeds through the full pipeline, blend and all:

    per-bet EV sd  median 0.0182 (reps=1)  ->  0.0091 at the shipped reps=4
    90th pct 0.0426, max 0.0674 at reps=1

So a reported EV of exactly 0 sits within 2sd of +3.6% on sampling noise alone at reps=1, and
+1.8% at reps=4. EV_MIN = 0.03 is ~3.3sd of the shipped configuration's noise. It is chosen from
that measurement, NOT tuned on the current board — picking 0.05 would leave exactly one flag
standing, which is fitting to a single event rather than to the noise.

WHAT THIS DOES NOT FIX, and it matters more than the floor. A 3% EV floor filters sampling noise;
it cannot filter MODEL error, which is far larger and unquantified. BLEND_W's bootstrap CI spans
[0.00, 1.00], and moving it inside that interval swings per-bet EV by roughly +/-8 points — several
times the floor being imposed here. On the only scale-matched test available the model is a coin
flip against the market. So this makes the gate ARITHMETICALLY honest; it does not make the
surviving bets proven. They remain paper-only until settled top-N outcomes exist.

BIRDIES NEED NO CHANGE. That stream measures `edge = ours - 1/od` against the RAW offered price, so
EV = od * edge > 0.05 for any od > 1 whenever the 0.05 edge gate passes. It already carries an
implicit EV floor above this one, by construction rather than by accident.
"""
import ast
import io

p = "pga_e3.py"
s = io.open(p, encoding="utf-8").read()

anchor = "TN_RATIO_MIN = 1.15"
const = '''EV_MIN = 0.03           # MEASURED 2026-07-30. A bet must clear +3% EV AT THE OFFERED PRICE, not
                        # merely beat the devigged fair by an absolute probability margin — those
                        # are different tests and only this one accounts for the vig. Since
                        # od = N_eff/(fair*inv), EV = (p_bet/fair)/vig - 1, and the measured
                        # overround on these products is 1.21-1.29, so TN_RATIO_MIN=1.15 alone
                        # admitted guaranteed losers. Floor sized off Monte Carlo noise in the EV
                        # number itself: 6 seeds give a per-bet sd of 0.0182 at reps=1, 0.0091 at
                        # the shipped reps=4, so 0.03 is ~3.3sd. It filters SAMPLING noise only —
                        # model error is larger and unquantified (BLEND_W's CI alone swings EV by
                        # ~+/-8 points), so clearing this floor is necessary, never sufficient.
'''
if "EV_MIN" in s:
    print("  = EV_MIN already present")
else:
    assert anchor in s, "TN_RATIO_MIN anchor missing"
    s = s.replace(anchor, const + anchor, 1)

lines = s.split("\n")


def splice(pred, n_old, new_lines, tag):
    """Replace n_old lines starting at the first line matching pred. Located, not literal —
    two earlier patches died on hand-transcribed continuation-line indentation."""
    global lines
    if tag in s:
        print("  = %s already applied" % tag)
        return False
    i = next((k for k, l in enumerate(lines) if pred(l)), None)
    assert i is not None, "anchor not found: %s" % tag
    lines = lines[:i] + new_lines + lines[i + n_old:]
    return True


# ---- top-N: add the EV floor to the gate ----
if "and _blend(fair, ours) * od - 1.0 >= EV_MIN" not in s:
    i = next(k for k, l in enumerate(lines) if "elif (od >= TN_MIN_ODDS" in l)
    lines = lines[:i] + [
        "            elif (od >= TN_MIN_ODDS",
        "                  and TN_RATIO_MIN <= ours / max(fair, 1e-9) <= TN_RATIO_MAX",
        "                  and _blend(fair, ours) - fair >= TN_EDGE",
        "                  # EV AT THE OFFERED PRICE (2026-07-30). The three tests above are all",
        "                  # relative to the DEVIGGED fair; none of them knows what vig we pay. On a",
        "                  # 21-29% overround that gap passed guaranteed losers.",
        "                  and _blend(fair, ours) * od - 1.0 >= EV_MIN):",
    ] + lines[i + 3:]
    print("  + top-N gate: EV floor added")
else:
    print("  = top-N EV floor already applied")

# ---- matchups: same floor ----
if "_bet * odds - 1.0 >= EV_MIN" not in "\n".join(lines):
    i = next(k for k, l in enumerate(lines) if "if (_bet - _fair_side >= M_EDGE" in l)
    lines = lines[:i] + [
        "        if (_bet - _fair_side >= M_EDGE",
        "                and _ours_side / max(_fair_side, 1e-9) <= M_RATIO_MAX",
        "                and _bet * odds - 1.0 >= EV_MIN):",
    ] + lines[i + 2:]
    print("  + matchup gate: EV floor added")
else:
    print("  = matchup EV floor already applied")

s = "\n".join(lines)
ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + pga_e3.py written")
