"""Round-score Over/Under — SHADOW STREAM. The model's most native market, with one caveat.

WHY THIS IS THE PUREST TEST OF THE RULER. Every other stream is a DERIVATION: top-N needs a field
simulation and a pool devig, matchups need a pairwise comparison, birdies need a per-par hazard
model. A round-score O/U asks the ruler exactly the question it was built to answer — what will
this player shoot — and settles it against a two-way ~6% book.

MEASURED ON 15,426 LEAK-FREE PLAYER-ROUNDS ACROSS 40 EVENTS (as-of ratings, no lookahead):

    standardised residual z = (actual - predicted) / sigma
        sd   0.9959     <- sigma is right to 0.4%. The SHAPE is trustworthy.
        mean +0.1482    <- the LEVEL is not: ~0.41 strokes optimistic.
    tail coverage |z|>0.5 / 1.0 / 1.5 / 2.0 = 0.96 / 0.93 / 0.96 / 1.14 of normal expectation.

Sigma being right to 0.4% is the reason this stream is worth building at all: an O/U price is a
statement about the DISPERSION of a player's score, and ours matches reality almost exactly.

THE LEVEL BIAS IS WHY IT CANNOT BE PRICED NAIVELY. A +0.148 sigma offset translates into a
systematic 3-5 point underestimate of P(over) at every realistic line:

    line = pred-1.5  model .6978  realised .7509   gap -0.053
    line = pred-0.5  model .5684  realised .6166   gap -0.048
    line = pred+0.5  model .4310  realised .4744   gap -0.043
    line = pred+1.5  model .3016  realised .3308   gap -0.029

That gap is LARGER than the ~6% vig, so a naive build would bet UNDER almost every time and lose
steadily. It would also have looked superficially fine — the bets would cluster on one side, which
is the same signature the birdie stream's one-sidedness alarm was written to catch.

THE FIX IS STRUCTURAL, NOT A FITTED CONSTANT. Solve a single additive offset DELTA (in strokes) so
the model's MEAN P(over) across this event's two-sided lines equals the market's mean devigged
P(over), then bet only the player-relative deviations from that. This is the same discipline the
birdie stream uses for LAM, and it is honest for the same reason: the absolute scoring level of a
course on a given day is something the market can see (setup, agronomy, wind, pin sheet) and the
ruler cannot. We claim to know who beats the field, never what the field will shoot.

DELTA also absorbs the +0.148 bias measured above without anyone tuning a constant against it, so
no retrospective fit enters the live path.

SHADOW. New stream, new hypothesis under the v1.0 freeze. The gates below are inherited priors from
the top-N measurement, not evidence about this market. Constants live here so the v1.0 constant
fingerprint stays byte-identical.
"""
import math
import re
import statistics as st

RS_RATIO_MIN = 1.15     # inherited priors from the top-N ratio study, NOT evidence for this market
RS_RATIO_MAX = 2.0
RS_EDGE = 0.02
RS_EV_MIN = 0.03
RS_MIN_LINES = 6        # below this the DELTA anchor is fitted on too little and the level is
                        # guesswork — refuse rather than price an unanchored book. This is the
                        # lesson from the birdie stream, whose anchor needs 8 two-sided lines and
                        # silently priced unanchored when Rocket Classic R1 posted only 7.
ARMABLE = False         # flip only via the paired-SPRT adoption rule in pga_validate.py

_MKT = re.compile(r"^(.*?)\s+Round\s+(\d)\s+Score$", re.I)
_RUN = re.compile(r"^(.*?)\s+(Over|Under)\s+([\d.]+)$", re.I)


def _p_over(mu, sig, line):
    """P(score > line) for a continuous normal. Lines are always X.5 so no push exists."""
    if sig <= 0:
        return None
    return 1.0 - st.NormalDist(mu, sig).cdf(line)


def price(rows, R, norm, blend, spread):
    """[{stream, runner, market, odds, p_raw, p_bet, p_fair, edge, ev}] for round-score O/U.

    `R` is the raw rating map {player: (mu, sigma, ...)}; `spread` is pga_ruler.SPREAD so this
    stream and the simulator never disagree about the same player.
    """
    out = []
    quotes = {}                                        # (player, rnd, line) -> {side: odds}
    for mkt, mt, run, od in rows:
        if not od or od <= 1.0:
            continue
        m = _MKT.match(str(mkt).strip())
        rm = _RUN.match(str(run).strip())
        if not m or not rm:
            continue
        quotes.setdefault((m.group(1).strip(), int(m.group(2)), float(rm.group(3))),
                          {})[rm.group(2).lower()] = od
    two = {k: v for k, v in quotes.items() if "over" in v and "under" in v}
    if len(two) < RS_MIN_LINES:
        return out

    vals = [v[0] for v in R.values()]
    if not vals:
        return out
    rmean = sum(vals) / len(vals)

    def skill(player):
        v = R.get(player) or R.get(norm(player))
        if not v:
            return None
        return rmean + spread * (v[0] - rmean), v[1]

    fair = {}
    for k, v in two.items():
        io_, iu = 1.0 / v["over"], 1.0 / v["under"]
        fair[k] = io_ / (io_ + iu)
    usable = [k for k in two if skill(k[0])]
    if len(usable) < RS_MIN_LINES:
        return out

    # ---- solve DELTA so our mean P(over) matches the market's mean devigged P(over) ----
    target = sum(fair[k] for k in usable) / len(usable)

    def mean_over(delta):
        tot = 0.0
        for (pl, _r, line) in usable:
            mu, sig = skill(pl)
            tot += _p_over(mu + delta, sig, line) or 0.0
        return tot / len(usable)

    # DELTA lives on the ABSOLUTE score scale (~67-72), while ratings are DEVIATIONS centred
    # near zero — so the bracket must span the lines, not the ratings. A [-12, 12] bracket
    # pinned at its bound, drove every probability to 0.9998 and produced seven "under" flags
    # at +36% to +80% EV. Garbage, but plausible-looking garbage.
    _lines = [k[2] for k in usable]
    lo, hi = min(_lines) - 25.0, max(_lines) + 25.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if mean_over(mid) > target:
            hi = mid
        else:
            lo = mid
    delta = (lo + hi) / 2.0
    # REFUSE TO PRICE AN ANCHOR THAT DID NOT CONVERGE. If delta sits against a bracket edge the
    # level was never solved, and every downstream probability is a saturated artefact.
    if delta <= min(_lines) - 24.0 or delta >= max(_lines) + 24.0:
        return out
    if abs(mean_over(delta) - target) > 0.02:
        return out

    for (pl, rnd, line) in usable:
        mu, sig = skill(pl)
        po = _p_over(mu + delta, sig, line)
        if po is None:
            continue
        for side in ("over", "under"):
            od = two[(pl, rnd, line)][side]
            ours = po if side == "over" else 1.0 - po
            f = fair[(pl, rnd, line)] if side == "over" else 1.0 - fair[(pl, rnd, line)]
            if not (0 < f < 1):
                continue
            ratio = ours / f
            pb = blend(f, ours)
            ev = pb * od - 1.0
            if (RS_RATIO_MIN <= ratio <= RS_RATIO_MAX
                    and pb - f >= RS_EDGE and ev >= RS_EV_MIN):
                out.append({"stream": "E3-rscore" if ARMABLE else "E3-rscore-shadow",
                            "runner": f"{pl} {side} {line:g}",
                            "market": f"{pl} Round {rnd} Score",
                            "odds": od, "p_raw": round(ours, 4), "p_bet": round(pb, 4),
                            "p_fair": round(f, 6), "edge": round(pb - f, 3),
                            "ev": round(ev, 4), "shadow": not ARMABLE,
                            "_delta": round(delta, 3)})
    # ONE-SIDEDNESS IS A LEVEL ALARM, same as the birdie stream. With the level anchored to the
    # market both sides start from the same handicap, so an all-one-way split means DELTA is
    # wrong again — which is exactly how the bad bracket announced itself.
    _one_sided = out and len({r["runner"].rsplit(" ", 2)[-2] for r in out}) == 1
    if _one_sided and len(out) >= 4:
        return []
    return out
