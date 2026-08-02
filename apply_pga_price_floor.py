"""The PGA deficit is not spread across the book — it is all on sides the MARKET prices as dogs.

PROFILE OF THE 36 GRADED FLAGS (16-20, -5.37u):

    by claimed edge (p_bet - p_fair)        corr with winning  +0.053   <- orders NOTHING
    by market fair probability (p_fair)     corr with winning  +0.383   <- orders them well
    by model probability (p_bet)            corr with winning  +0.319   <- inherited from p_fair

    Every bet is a side where model > market by construction, and that gap is a near-constant
    +0.09 to +0.11 in EVERY price bucket. A constant offset carries no ordering information, which
    is exactly what corr(edge, win) = +0.05 says out loud. This is the signature
    project_pga_edge_forensics predicted in writing before this sample existed: a low-information
    model compressed toward the base rate, plus an ABSOLUTE edge threshold, manufactures "edge"
    wherever the market price sits far from the model's compressed centre — i.e. on longshots.

WITHIN BIRDIES ALONE (so this is not just "rscore is bad" — only 32% of birdies bets sit below
even money, against 91% of rscore bets, so the two are separable):

    p_fair 0.40-0.45   n=4    25.0%   -1.68u
    p_fair 0.45-0.50   n=4     0.0%   -4.00u
    p_fair 0.50-0.55   n=9    77.8%   +4.44u
    p_fair 0.55-0.60   n=3    66.7%   +0.53u
    p_fair 0.60-1.00   n=5    80.0%   +1.09u
    ------------------------------------------
    split at even money:  13-4 (+6.06u)  vs  1-7 (-5.68u)     Fisher two-sided p = 0.0072

Monotone across five buckets, not a spike at one, and the cut is EVEN MONEY — a landmark, not a
tuned number. Moving it to 0.52 or 0.55 scores worse (+2.15u, +1.61u), which is what a tuned cut
would not do.

THE FLOOR IS THE FIX THE OTHER STREAMS ALREADY GOT. On 2026-07-30 the top-N audit found the
absolute-edge test was "structurally excluding favourites, the only region where this model is
calibrated", and replaced it with a measured ratio band. Birdies was deliberately exempted because
it had passed a leak-free reliability test. Its live record now says the exemption was wrong in
precisely the predicted direction. B_RATIO_MAX=1.6 was supposed to be the guard here and is INERT:
it would have blocked 0 of 25 bets, worst ratio seen 1.52.

WHAT WAS REJECTED, AND WHY IT IS NOT SHIPPED. Blending birdies toward the market like every other
stream (BLEND_W=0.40) was the other obvious candidate and it LOSES: -1.72u at edge>=0.03, -2.65u at
0.04, -2.10u at 0.05, against a +0.38u baseline. It shrinks favourites and dogs alike, so it strips
the bets that win to remove the ones that lose. Floor plus blend (+2.28u) is worse than floor alone
(+6.06u). Standing rule: do not change a model that works because a change backtests poorly on the
bets actually selected.

SCOPE — the floor applies to the two ROUND-SCOPED streams only.
  * birdies + round-score: this is where the evidence is, and where a near-coin-flip market is the
    natural shape of the product.
  * top-N is NOT touched. Its bets are structurally longshots (p_fair 0.07-0.22); a 0.50 floor
    would delete the entire stream, and it already carries the measured 986-runner ratio band that
    is the analogous fix.
  * matchups are NOT touched. They show the same signature — all three open ones are dogs (0.418,
    0.418, 0.327) and the audit noted the model backing the underdog in 12 of 14 markets — but G2
    has ZERO graded outcomes. Applying an unmeasured filter to a stream with no evidence is the
    same mistake in the other direction. Watch it; do not act on it yet.

REJECTED FLAGS ARE KEPT AS A SHADOW, NOT DELETED. n=36 is not enough to be sure, so the filter has
to keep earning its place: rejects are retagged `-lowprice`, still graded, and excluded from the
board record. If the floor is wrong, the -lowprice line will say so.
"""
import ast
import io
import shutil

P = "pga_e3.py"
s = io.open(P, encoding="utf-8").read()

if "PRICE_FLOOR" in s:
    print("  = already applied")
    raise SystemExit(0)

CONST = '''PRICE_FLOOR = 0.50      # MEASURED 2026-08-02 on 36 graded flags. A round-scoped bet must be
                        # on a side the MARKET does not price as a dog. Splitting birdies at even
                        # money: 13-4 +6.06u above vs 1-7 -5.68u below, Fisher p=0.0072, monotone
                        # across five buckets. The claimed edge itself orders nothing (corr +0.053
                        # with winning) while the market price orders well (+0.383) — so the edge
                        # says WHICH side, and the price says WHETHER to bet at all.
                        #
                        # This is the fix top-N already received on 2026-07-30 for the identical
                        # finding (absolute edge test "structurally excluding favourites"). Birdies
                        # was exempted then; the live record withdrew the exemption.
                        #
                        # NOTE ON BASIS: birdies stores p_fair as raw 1/odds (vig included), rscore
                        # stores it devigged. The floor is applied to each stream's OWN p_fair
                        # because that is the quantity the backtest above was run on — restating it
                        # on a common basis would invalidate the number it is set from.
                        #
                        # Set to 0.0 to disarm.
'''

anchor = "M_EDGE = 0.06"
assert anchor in s, "constant anchor"
s = s.replace(anchor, CONST + anchor, 1)

FILT = '''    # ---- PRICE FLOOR on round-scoped streams (2026-08-02) ----
    # See PRICE_FLOOR. Rejected flags are RETAGGED, never dropped: they still price, still log,
    # still grade, and are excluded from the board record — so the floor keeps accumulating the
    # evidence that would overturn it. Deleting them would make the filter unfalsifiable.
    _floored = 0
    if PRICE_FLOOR > 0:
        for _pv in preview:
            _st = _pv.get("stream") or ""
            if not (_st.startswith("E3-birdies") or _st.startswith("E3-rscore")):
                continue                       # top-N is structurally longshot; matchups have n=0
            if (_pv.get("p_fair") or 0.0) >= PRICE_FLOOR:
                continue
            _pv["stream"] = _st + "-lowprice"
            _pv["shadow"] = True               # never competes with v1.0 for a board slot
            _floored += 1
    if _floored:
        print(f"  price floor: {_floored} flag(s) below p_fair {PRICE_FLOOR:.2f} "
              f"retagged -lowprice (logged + graded, off the board)")

'''

anchor2 = "    # DEDUPE (2026-07-29): the same underlying market reaches us under several mtypes"
assert anchor2 in s, "dedupe anchor"
s = s.replace(anchor2, FILT + anchor2, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/pga_e3.prefloor.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + PRICE_FLOOR=0.50 on birdies + round-score; rejects retagged -lowprice, not deleted")
