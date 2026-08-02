"""Make-the-cut pricing — SHADOW STREAM, candidate hypothesis against the frozen v1.0 baseline.

WHY THIS MARKET IS THE BEST STRUCTURAL FIT FOR THIS MODEL, measured rather than asserted:

  * VIG. Two-way markets on this book run 5.8-6.0% against 21.9-29.5% on top-N and 44% on
    outrights. Since EV = (p_bet/fair)/vig - 1, the break-even ratio IS the vig: 1.06x here versus
    1.22-1.29x for top-N. This model's demonstrated edge is small, and a small edge dies against a
    25% overround while surviving a 6% one.
  * NO TAIL. The model's ONE proven weakness is longshot over-prediction — bottom-decile top-20
    probabilities realised 0.010 against a predicted 0.055. A cut market has no longshots: on a
    144-man field the model's cut probabilities span 0.24 to 0.80, with 104 of 144 inside
    0.35-0.65. It prices exactly the mid-range where the model is calibrated (reliability slope
    1.043) and structurally cannot bet the region where it is not.
  * HORIZON. 36 holes sits between the measured single-round ordering ceiling (0.604) and the
    72-hole ceiling (0.683), so it keeps materially more signal than any one-round market.
  * SIMPLEST DEVIG. Two-way normalisation has none of the failure modes this codebase actually
    found in top-N — no nominal-N normaliser, no pool-completeness assumption, no ties-inclusive
    ambiguity. Every one of those bugs is structurally impossible here.

WHY IT IS SHADOW AND NOT ARMED. It is a NEW STREAM, therefore a NEW HYPOTHESIS under the v1.0
freeze. Its constants have never been validated on a settled cut bet — the ratio band and EV floor
below are inherited from top-N measurements, which is a PRIOR, not evidence. It logs to the ledger
under a `-shadow` stream tag so a prospective record accumulates, and the validator keeps it out of
the v1.0 SPRT entirely. Under the pre-registered adoption rule it must beat the frozen baseline on
a PAIRED SPRT over >= 100 prospective settled bets before it can arm. Assuming it will work because
the structural argument above is tidy is exactly the reasoning that produced the tail bug.

KNOWN PROPERTY OF THE ONE-SIDED PATH, found in testing. There, `vig = inv / n_eff` and `n_eff`
comes from the MODEL, so a systematic model-vs-market gap across the whole pool reads as an
implausible overround and the stream declines to price at all. That is a SAFE failure — it refuses
rather than betting every runner in the pool, which is what the top-N normaliser bug did — but it
fails SILENTLY. The shadow record must therefore always be read next to a priced/skipped count, or
"no flags" will be mistaken for "no edge" when it actually means "the stream switched itself off".
The two-way path is immune: its vig is computed from the Yes/No pair alone and never touches the
model.

Constants live HERE, not in pga_e3, so the v1.0 constant fingerprint stays byte-identical and the
freeze can still prove that no scoring constant moved.
"""

CUT_RATIO_MIN = 1.15    # inherited from the top-N measurement (inside 2x the model is accurate to
CUT_RATIO_MAX = 2.0     # 1.06-1.10x; beyond it, over by 2.08-2.48x). A PRIOR for this market, not
                        # evidence — no settled cut bet has ever tested it.
CUT_EDGE = 0.02         # absolute floor; with the cap it implies fair >= 0.02, though a cut market
                        # never approaches that anyway.
CUT_EV_MIN = 0.03       # ~3.3 sd of the measured per-bet Monte Carlo EV noise at reps=4.
CUT_VIG_MIN = 1.01      # a book paying out more than it takes is a data error, not a gift.
CUT_VIG_MAX = 1.30      # tighter than top-N's 1.75: this is a two-way market and should price near
                        # 1.06. Anything above 1.30 is not a clean make/miss book.
CUT_MIN_RUNNERS = 8     # below this a one-sided pool cannot be normalised meaningfully.
ARMABLE = True          # ARMED 2026-07-30 by explicit instruction, after the trade-off was stated:
                        # armed cut bets enter the v1.0 record, so the paired-adoption test loses
                        # its clean control group. The stream tag stays distinct (`E3-cut`) so the
                        # two populations can still be separated ANALYTICALLY in every report —
                        # that is the only part of the control that survives arming.


def _norm(s):
    import pga_ruler as RU
    return RU.norm(s)


def price(rows, sim, blend, field_norm=None):
    """[{stream, runner, market, odds, p_raw, p_bet, p_fair, edge, ev}] for make-the-cut.

    Handles BOTH structures the book may post, decided from the data rather than assumed:

      two-way   one market per player with a Yes/No pair  -> fair = (1/od)/(1/od_yes + 1/od_no)
      one-sided one price per player across a pool        -> fair = (1/od) * N_eff / inv, with
                N_eff the model's expected cut-makers AMONG THE PRICED RUNNERS ONLY

    That second form is the priced-subset normaliser, not the nominal 70 — normalising a partial
    pool to the full cut size is the exact bug that made top-N ratios read 15% low.
    """
    from collections import defaultdict
    out = []
    cut_rows = [(mkt, mt, run, od) for mkt, mt, run, od in rows
                if od and od > 1.0
                and ("CUT" in str(mt).upper() or "cut" in str(mkt).lower())]
    if not cut_rows:
        return out

    def model_p(name):
        v = sim.get(name) or sim.get(_norm(name)) or {}
        return v.get("cut")

    # ---- structure detection: dedupe first, then look at runners per market ----
    by_mkt = defaultdict(dict)
    for mkt, mt, run, od in cut_rows:
        cur = by_mkt[mkt].get(run)
        if cur is None or od < cur:
            by_mkt[mkt][run] = od
    two_way = [m for m, d in by_mkt.items() if len(d) == 2]

    def _emit(runner, od, fair, p, mkt):
        if p is None or not (0 < fair < 1):
            return
        ratio = p / max(fair, 1e-9)
        pb = blend(fair, p)
        ev = pb * od - 1.0
        if (CUT_RATIO_MIN <= ratio <= CUT_RATIO_MAX
                and pb - fair >= CUT_EDGE and ev >= CUT_EV_MIN):
            out.append({"stream": "E3-cut" if ARMABLE else "E3-cut-shadow",
                        "runner": runner, "market": str(mkt)[:60],
                        "odds": od, "p_raw": round(p, 4), "p_bet": round(pb, 4),
                        "p_fair": round(fair, 6), "edge": round(pb - fair, 3),
                        "ev": round(ev, 4), "shadow": not ARMABLE})

    if len(two_way) >= max(1, len(by_mkt) // 2):
        # YES/NO pairs. The player is in the market string, the side in the runner string.
        for mkt, d in by_mkt.items():
            if len(d) != 2:
                continue
            (ra, oa), (rb, ob) = list(d.items())
            vig = 1 / oa + 1 / ob
            if not (CUT_VIG_MIN <= vig <= CUT_VIG_MAX):
                continue
            for rn, od in ((ra, oa), (rb, ob)):
                low = rn.lower()
                yes = ("miss" not in low and "not" not in low and "no" != low.strip())
                who = str(mkt)
                for tok in (" To Make The Cut", " to make the cut", " Make Cut", " - Yes", " - No"):
                    who = who.replace(tok, "")
                p = model_p(who.strip())
                if p is None:
                    continue
                _emit(f"{who.strip()} {'make' if yes else 'miss'}", od,
                      (1 / od) / vig, p if yes else 1 - p, mkt)
    else:
        # One price per player across a pool: normalise to the model's expected cut-makers
        # AMONG THE PRICED RUNNERS, never to the nominal cut size.
        pool = {}
        for mkt, d in by_mkt.items():
            for run, od in d.items():
                if field_norm and _norm(run) not in field_norm:
                    continue
                if run not in pool or od < pool[run]:
                    pool[run] = od
        if len(pool) < CUT_MIN_RUNNERS:
            return out
        inv = sum(1 / o for o in pool.values())
        n_eff = sum(model_p(r) or 0.0 for r in pool)
        if n_eff <= 0:
            return out
        vig = inv / n_eff
        if not (CUT_VIG_MIN <= vig <= CUT_VIG_MAX):
            return out
        for run, od in pool.items():
            _emit(run, od, (1 / od) * n_eff / inv, model_p(run), "TO_MAKE_THE_CUT")
    return out
