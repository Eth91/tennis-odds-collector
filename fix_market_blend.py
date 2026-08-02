"""Bet the BLEND of model and market, not the raw model.

The conditional-information test (986 priced+rated runners, 9 majors, real FD/DK closes, graded on
actual finishes) showed the model carries genuine incremental information over the closing line —
top-20 z=+3.54, LR chi2 12.60, p=0.002 — but nowhere near enough to justify betting its raw number.
Fitting the joint model in UNSTANDARDISED logit space, on probabilities that already have the
shipped SHAPE_SLOPE=1.30 recalibration applied:

    logit P(top20) = 2.329 + 0.602*logit(market) + 0.544*logit(model)
    -> implied model weight 0.474

BLEND_W is set to 0.40, BELOW that estimate, on purpose. The market predictor available for fitting
is the OUTRIGHT close, not a top-20 price — no historical top-N prices exist for golf (The Odds API
returns 422 on h2h). A correctly matched top-20 price would predict top-20 better than an outright
price does, so b1 would rise and 0.474 is an UPPER BOUND on what the model deserves. 0.40 is also
what the earlier standardised fit gave. Sizing at or under the bound is the conservative side.

WHY A CONVEX BLEND RATHER THAN THE FITTED EQUATION. Applying `a + b1*logit(mkt) + b2*logit(model)`
directly would be a bug: a=2.329 and b1+b2=1.146, so the formula returns something other than the
market price even when the model AGREES with the market exactly — it would manufacture an edge out
of nothing. The convex form below is self-anchoring: ours == fair returns fair exactly, so agreement
can never produce a bet. Only DISAGREEMENT can, which is the whole point.

Effect on a disagreement, since the blend scales the log-odds edge by w:
    raw 1.5x -> 1.21x     raw 2.0x -> 1.39x     raw 3.0x -> 1.68x

ORDER OF OPERATIONS. The ratio gate stays on the RAW model probability, because that is what the
2.0 cap was measured against (raw model/market is the diagnostic of model error). The blend is then
what we actually believe and price off. Gate on trust; bet on the blend.

BIRDIES ARE DELIBERATELY NOT BLENDED. Their level is already market-anchored by the LAM bisection,
so a further blend would shrink toward the market twice. They are also the one stream with a passed
probability-space reliability test (1.06 against the 0.85 bar, leak-free).
"""
import ast
import io

p = "pga_e3.py"
s = io.open(p, encoding="utf-8").read()

anchor = "TN_RATIO_MIN = 1.15"
const = '''BLEND_W = 0.40          # MEASURED 2026-07-30. We bet the BLEND of market and model, never the raw
                        # model. Joint unstandardised fit on 986 runners / 9 majors with real closes,
                        # on already-recalibrated probabilities:
                        #     logit P(top20) = 2.329 + 0.602*logit(mkt) + 0.544*logit(model)
                        # -> model weight 0.474. Set BELOW it at 0.40 because the market predictor
                        # available for fitting is the OUTRIGHT close, not a top-20 price (no
                        # historical top-N golf prices exist — h2h returns 422), so a matched price
                        # would score better and 0.474 is an UPPER bound. Set to 1.0 to bet the raw
                        # model again, which the audit showed is not defensible.
'''
if "BLEND_W" in s:
    print("  = BLEND_W already present")
else:
    assert anchor in s, "TN_RATIO_MIN anchor missing"
    s = s.replace(anchor, const + anchor, 1)

helper = '''

def _blend(fair, ours, w=None):
    """Convex blend of market and model in LOG-ODDS space.

    Self-anchoring by construction: ours == fair returns fair exactly, so agreeing with the market
    can never manufacture an edge. Using the raw fitted regression instead would, since its
    intercept is non-zero and its coefficients do not sum to 1.
    """
    import math as _m
    w = BLEND_W if w is None else w
    f = min(max(float(fair), 1e-9), 1 - 1e-9)
    o = min(max(float(ours), 1e-9), 1 - 1e-9)
    lf = _m.log(f / (1 - f))
    lo = _m.log(o / (1 - o))
    return 1.0 / (1.0 + _m.exp(-((1.0 - w) * lf + w * lo)))

'''
if "def _blend(" in s:
    print("  = _blend already present")
else:
    a2 = "\ndef latest_event_rows():"
    assert a2 in s, "latest_event_rows anchor missing"
    s = s.replace(a2, helper + "\ndef latest_event_rows():", 1)

# ---- top-N: gate on the RAW ratio, then price the BLEND ----
old_tn = '''            elif (ours - fair >= TN_EDGE and od >= TN_MIN_ODDS
                  and TN_RATIO_MIN <= ours / max(fair, 1e-9) <= TN_RATIO_MAX):
                preview.append({"stream": "E3-top%d" % N, "runner": run, "market": mt[:40],
                                "odds": od, "edge": round(ours - fair, 3)})'''
new_tn = '''            elif (od >= TN_MIN_ODDS
                  and TN_RATIO_MIN <= ours / max(fair, 1e-9) <= TN_RATIO_MAX
                  and _blend(fair, ours) - fair >= TN_EDGE):
                # gate on the RAW ratio (that is what the 2.0 cap was measured against), but
                # price off the BLEND — what we actually believe once the market is weighted in
                _pb = _blend(fair, ours)
                preview.append({"stream": "E3-top%d" % N, "runner": run, "market": mt[:40],
                                "odds": od, "edge": round(_pb - fair, 3),
                                "p_raw": round(ours, 4), "p_bet": round(_pb, 4),
                                "ev": round(_pb * od - 1.0, 4)})'''
if '"p_bet"' in s:
    print("  = top-N already prices the blend")
else:
    assert old_tn in s, "top-N gate anchor missing (run fix_tail_and_threshold.py first)"
    s = s.replace(old_tn, new_tn, 1)

# ---- matchups ----
old_m = '''        if pe >= M_EDGE and _ours_side / max(_fair_side, 1e-9) <= M_RATIO_MAX:
            preview.append({"stream": "E3-match", "runner": side, "market": mkt[:60],
                            "odds": odds, "edge": round(pe, 3)})'''
new_m = '''        _bet = _blend(_fair_side, _ours_side)
        if (_bet - _fair_side >= M_EDGE
                and _ours_side / max(_fair_side, 1e-9) <= M_RATIO_MAX):
            preview.append({"stream": "E3-match", "runner": side, "market": mkt[:60],
                            "odds": odds, "edge": round(_bet - _fair_side, 3),
                            "p_raw": round(_ours_side, 4), "p_bet": round(_bet, 4),
                            "ev": round(_bet * odds - 1.0, 4)})'''
if "_bet = _blend(_fair_side" in s:
    print("  = matchups already price the blend")
else:
    assert old_m in s, "matchup gate anchor missing"
    s = s.replace(old_m, new_m, 1)

ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + pga_e3.py: BLEND_W + _blend(); top-N and matchups now gate on raw, price on blend")
