"""⛳ E3 — RULER RESIDUAL meter (matchups, top-N, outrights) — GATED BEHIND G2, by code.

Runs every golf cron pass: refreshes results (which also feeds the G2 gate), refits the
ruler, prices the live FanDuel board, and computes residuals vs the devigged prices.

THE GATE IS IN THE CODE, NOT IN A PROMISE: until g2_gate() returns PASS on >=15 real closed
matchups, residuals are PREVIEW-ONLY (rendered on the board, clearly labeled, never logged
as paper flags) — a ruler that hasn't proven it can track the close cannot be allowed to
accumulate a paper record that looks like evidence. The week G2 goes green, flags start
logging themselves (stream E3-*) into the same paper ledger + tripwire as E1.

Devig conventions: matchbets = two-way normalization. Top-N/outrights are one-sided books:
fair p_i = (1/odds_i) * N / sum_j(1/odds_j) — the field-wide overround scaled to N expected
winners. Pre-registered flag knobs (constitution law 7 — set BEFORE any result is seen):
matchups |edge| >= 0.06; top-N edge >= 0.04 & odds >= 1.5; outrights EV >= +15% & our
p >= 1.3x fair. These do not move after launch except by a written decision.
"""
import datetime as dt
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import pga_ruler as RU
import pga_e1 as E1
import pga_field as F

HERE = Path(__file__).resolve().parent
LINES = HERE / "golf_lines.sqlite"
PAPER = HERE / "pga_paper.sqlite"

M_EDGE = 0.06
M_RATIO_MAX = 1.6       # PRUDENTIAL, not measured — G2 is still n=0, so there is no matchup-specific
                        # evidence. Carried over from the top-N ratio result because the audit found
                        # the same signature: the model backed the UNDERDOG in 12 of 14 markets, with
                        # every model probability inside 0.430-0.599 against a market spanning
                        # 0.211-0.682. Revisit once G2 has a real sample.
B_RATIO_MAX = 1.6       # loose guard-rail only. Birdies are the one stream that HAS passed a
                        # probability-space reliability test (1.06 vs the 0.85 bar, leak-free), so
                        # they are deliberately not retuned on evidence borrowed from top-N.
TN_EDGE = 0.02          # LOWERED 2026-07-30 from 0.04. The absolute test is no longer doing the
                        # selecting — the ratio band below is — so this is now just a floor that
                        # keeps trivial absolute edges out. Floor and cap together imply a minimum
                        # fair probability with no extra constant: fair*(RATIO_MAX-1) >= TN_EDGE,
                        # i.e. fair >= 0.02. The tail exclusion is DERIVED, not asserted.
BLEND_W = 0.40          # MEASURED 2026-07-30. We bet the BLEND of market and model, never the raw
                        # model. Joint unstandardised fit on 986 runners / 9 majors with real closes,
                        # on already-recalibrated probabilities:
                        #     logit P(top20) = 2.329 + 0.602*logit(mkt) + 0.544*logit(model)
                        # -> model weight 0.474. Set BELOW it at 0.40 because the market predictor
                        # available for fitting is the OUTRIGHT close, not a top-20 price (no
                        # historical top-N golf prices exist — h2h returns 422), so a matched price
                        # would score better and 0.474 is an UPPER bound. Set to 1.0 to bet the raw
                        # model again, which the audit showed is not defensible.
VIG_MIN = 1.01          # implied overround = inv / N_eff, now that both cover the SAME runners.
VIG_MAX = 1.75          # MEASURED across all six live top-N products: 1.209-1.373. Below 1.0 the
                        # book would be paying out more than it takes, which is a data error, not a
                        # gift. Above 1.75 the pool is not one N-winner market — duplicated or merged
                        # pools land at 2.4x+. Replaces the old inv-vs-3*N_eff net, which could not
                        # mean anything while N_eff and inv were counted over different populations.
TN_RATIO_MIN = 1.15     # MEASURED 2026-07-30. Bucketing 986 runners by (model/market) and grading
TN_RATIO_MAX = 2.0      # on top-20 (162 positives): inside 2x the model is accurate (1.06-1.10x
                        # realised), beyond 2x it over-predicts by 2.08x (n=134) and 2.48x (n=192).
                        # Past 2x the disagreement IS our error, so refuse to bet it. This replaces
                        # `ours - fair >= 0.04`, which on a 5x-inflated tail fired 11 flags in the
                        # longest-odds quartile against 3 in the shortest — structurally excluding
                        # favourites, the only region where this model is calibrated.
TN_MIN_ODDS = 1.5
OUT_EV = 0.15
OUT_RATIO = 1.3
# Gated off 2026-07-30 by the real-price backtest above: 55% of the field
# flagged, -85.6% ROI on 528 bets, and a 39.5% median overround.
OUTRIGHT_ARMABLE = False



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


def latest_event_rows():
    con = sqlite3.connect(LINES)
    ev = con.execute("SELECT event, COUNT(*) c FROM golf_lines WHERE collected_at >= "
                     "datetime('now','-1 day') AND event LIKE '%PGA%' AND event NOT LIKE "
                     "'%202_'||'7%' GROUP BY event ORDER BY c DESC LIMIT 1").fetchone()
    if not ev:
        con.close()
        return None, []
    evn = ev[0]
    ts = con.execute("SELECT MAX(collected_at) FROM golf_lines WHERE event=?", (evn,)).fetchone()[0]
    rows = con.execute("SELECT market, mtype, runner, odds FROM golf_lines "
                       "WHERE event=? AND collected_at=?", (evn, ts)).fetchall()
    con.close()
    return evn.strip(), rows


def main():
    RU.crawl((2026,))                       # fresh results -> ratings AND the G2 sample
    R_raw, _ = RU.fit()
    R = {RU.norm(k): v for k, v in R_raw.items()}
    passed, n_g2 = RU.g2_gate(verbose=True)
    armed = bool(passed)

    evn, rows = latest_event_rows()
    if not evn:
        print("e3: no active PGA event in the collector — nothing to price")
        return
    print(f"e3: pricing {evn}  (G2 {'PASS — flags ARMED' if armed else 'pending n=%d — preview only' % n_g2})")

    preview, flags = [], []
    cfit = {}                     # filled by the field block below; matchups tolerate empty
    now = dt.datetime.utcnow().replace(microsecond=0).isoformat()

    # ---- matchbets (two-way) ----
    by_m = defaultdict(list)
    for mkt, mt, run, od in rows:
        if "Matchbet" in mkt and od and od > 1.0:
            by_m[mkt].append((run, od))
    for mkt, rr in by_m.items():
        if len(rr) != 2:
            continue
        (a, oa), (b, ob) = rr
        nrounds = 1 if ("Round" in mkt or "1st" in mkt) else 4
        p = RU.matchup_prob(R, a, b, rounds=nrounds, course_fit=cfit)
        if p is None:
            continue
        fair = (1 / oa) / (1 / oa + 1 / ob)
        edge = p - fair
        side, odds, pe = (a, oa, edge) if edge > 0 else (b, ob, -edge)
        _ours_side = p if side == a else (1 - p)
        _fair_side = fair if side == a else (1 - fair)
        _bet = _blend(_fair_side, _ours_side)
        if (_bet - _fair_side >= M_EDGE
                and _ours_side / max(_fair_side, 1e-9) <= M_RATIO_MAX):
            preview.append({"stream": "E3-match", "runner": side, "market": mkt[:60],
                            "odds": odds, "edge": round(_bet - _fair_side, 3),
                            "p_raw": round(_ours_side, 4), "p_bet": round(_bet, 4),
                            "ev": round(_bet * odds - 1.0, 4)})

    # ---- top-N + outrights (one-sided) ----
    field = [(c.get("athlete") or {}).get("displayName") for c in F.competitors()]
    field = [f for f in field if f]
    # COURSE FIT + WAVE-CORRELATED CUT (blind spots #3 and #5). course_fit is already
    # shrunk inside pga_context; wave comes from the real tee sheet, and wave_shift scales
    # the measured wind gap between the two waves into strokes.
    cfit, wave, wshift = {}, {}, 0.0
    try:
        import pga_context as C
        for p_ in field:
            d_, n_ = C.course_fit(p_, evn)
            if n_ >= 2:
                cfit[p_] = d_
        import pga_field as _PF, pga_e1 as _E1, statistics as _st
        import pga_wave as _W, pga_birdies as _B
        la, lo = _PF.coords()
        wnote = "no orchestrator id"
        tid_ = None
        try:
            tid_ = _B.tid_for_name(evn)
        except Exception:                                          # noqa: BLE001
            tid_ = None
        if tid_:
            # refresh THIS event's sheet every run: tee times post Tue/Wed and the whole
            # point of reading the orchestrator is to see them the moment they land
            try:
                _W.harvest_tees(tids=[(tid_, evn)], verbose=False)
            except Exception:                                      # noqa: BLE001
                pass
            wave, wshift, wnote = _W.wave_shift_for(tid_, lat=la, lon=lo)
        if not wave:
            # FALLBACK: ESPN's competitor stamp, which only fills in late. Uses the fitted
            # beta, not the old 0.04 placeholder, so the degraded path is still defensible.
            tt = _PF.tee_times()
            if tt:
                hrs = sorted(tt.values())
                med = hrs[len(hrs) // 2]
                for p_, t_ in tt.items():
                    wave[p_] = "am" if t_ <= med else "pm"
                if la is not None:
                    w_ = _E1.wind_hours(la, lo, days=3)
                    am = [_E1.exposure(w_, t_) for p_, t_ in tt.items()
                          if wave.get(p_) == "am"]
                    pm = [_E1.exposure(w_, t_) for p_, t_ in tt.items()
                          if wave.get(p_) == "pm"]
                    am = [x for x in am if x is not None]
                    pm = [x for x in pm if x is not None]
                    if am and pm:
                        _f = _W.fit_wave(verbose=False)
                        wshift = (_f.get("beta", 0.02) * (_st.mean(pm) - _st.mean(am))
                                  + _f.get("intercept", 0.0))
                        wnote = "ESPN fallback sheet"
        print(f"  ruler: course-fit players {len(cfit)}, wave split {len(wave)}, "
              f"wave shift {wshift:+.2f} strokes [{wnote}]")
    except Exception as _xe:
        print(f"  ruler: context unavailable ({str(_xe)[:40]})")
    # reps=4 halves Monte Carlo noise (worst case 0.70pt on top-20, ~14% of the 5pt edge
    # threshold) without growing peak memory on this box
    sim = RU.simulate(R, field, course_fit=cfit, wave=wave,
                      wave_shift=wshift, reps=4) if field else {}
    # DEDUPE BEFORE DEVIG (2026-07-29) — this was manufacturing fake +20-27% edges.
    # The one-sided devig normalizes by sum(1/odds) over the market, so DUPLICATE runners
    # (the same top-20 market arrives as TOP_20_FINISH_IMG, TOP_20_FINISH_(INCL._TIES),
    # AND again from the competition page) inflate the normalizer: a pool that should imply
    # ~20 qualifiers implied 434, which crushed every `fair` and made the sim look like it
    # had a huge edge on everyone. The sim itself is sound — it sums to exactly 1/5/10/20/70
    # across the field — so the error was entirely in this pooling. Keep ONE price per
    # (market-family, runner): the SHORTEST (the sharpest posted number).
    # SEPARATE PRODUCTS DEVIG SEPARATELY (2026-07-30, bug #8). "Top 20" and "Top 20 Finish
    # (Incl. Ties)" are DIFFERENT markets with different payouts. Collapsing them into one
    # family and keeping the shortest price per runner inflated the normaliser: measured live,
    # 1,620 rows implying 343 qualifiers plus 253 implying 45, merged to imply 29.2 against a
    # target of 20. Because fair = (1/od) * N / inv, that DEFLATED every fair probability ~28%
    # and the flag is `ours - fair >= TN_EDGE` — so a true fair of 0.30 read 0.216 and handed
    # out +8.4 points of edge that did not exist. Same mechanism as the original +20-27% bug;
    # the 0.4N-3N guard passes 29.2. Keying on the FULL mtype keeps the products apart.
    # Also restrict each pool to runners actually in this event's field: a pool with more
    # entrants than the field is pooling something foreign.
    field_norm = {RU.norm(f) for f in field} if field else set()
    groups = defaultdict(dict)
    for mkt, mt, run, od in rows:
        if od and od > 1.0 and mt and ("TOP_" in mt and "FINISH" in mt or mt == "OUTRIGHT_BETTING"):
            if field_norm and RU.norm(run) not in field_norm:
                continue
            cur = groups[mt].get(run)
            if cur is None or od < cur:
                groups[mt][run] = od
    groups = {k: list(v.items()) for k, v in groups.items()}

    def _n_for(mt_):
        if mt_ == "OUTRIGHT_BETTING":
            return 1
        d = "".join(ch for ch in str(mt_).split("_FINISH")[0] if ch.isdigit())
        return int(d) if d in ("5", "10", "20") else None

    for mt, rr in groups.items():
        N = _n_for(mt)
        if not N or len(rr) < 25 or not sim:
            continue
        # TIES-INCLUSIVE PRODUCTS ARE NOT PRICEABLE HERE (bug #10). "Top 20 Finish (Incl.
        # Ties)" pays on 22-26 players, not 20, so N is wrong AND simulate() draws continuous
        # normals — exact ties have probability zero and its top20 is strictly rank<20, a
        # ties-EXCLUSIVE quantity. Comparing that to a ties-inclusive price is a category
        # error in the direction that manufactures edge. Pricing these needs integer-score
        # simulation with tied ranks; until then, skip. Skipping a market is free.
        # TIES-INCLUSIVE PRODUCTS ARE NOW PRICEABLE. simulate() returns tie-aware probabilities
        # (integer scores), so use the *_ties key AND replace the nominal N with the model's own
        # expected qualifier count — these products pay 22-26 players, not 20, and devigging
        # against 20 is exactly what inflated the edge before.
        is_ties = "TIE" in str(mt).upper()
        key = ({1: "win_ties", 5: "top5_ties", 10: "top10_ties", 20: "top20_ties"}
               if is_ties else {1: "win", 5: "top5", 10: "top10", 20: "top20"})[N]
        if not any(key in (v or {}) for v in sim.values()):
            print(f"  skip {mt}: sim has no {key}")
            continue
        # NORMALISER OVER THE PRICED SUBSET (2026-07-30). `inv` only ever covered the runners the
        # book prices, so N_eff must too. Normalising 102 priced runners — who hold 17.07 of the 20
        # top-20 slots — as if they held all 20 inflated every fair by ~17%, which DEFLATED every
        # ours/fair ratio by ~15% and made the ratio gate read low on the market carrying most of
        # the board. Conservative for the edge, permissive for the safety gate; the gate matters.
        N_eff = sum((sim.get(run) or sim.get(RU.norm(run)) or {}).get(key, 0.0)
                    for run, _od in rr)
        if N_eff <= 0:
            continue
        inv = sum(1 / od for _, od in rr)
        _vig = inv / N_eff
        if not (VIG_MIN <= _vig <= VIG_MAX):
            # inv/N_eff is now a like-for-like overround, so an implausible value means the pool is
            # not one N-winner market (duplicated, merged, or partially collected).
            print(f"  skip {mt}: implied vig {_vig:.3f} outside [{VIG_MIN}, {VIG_MAX}] "
                  f"({len(rr)} priced, N_eff {N_eff:.2f})")
            continue
        print(f"  {mt}: {len(rr)} priced, N_eff {N_eff:.2f} (nominal {N}), implied vig {_vig:.3f}")
        for run, od in rr:
            fair = (1 / od) * N_eff / inv
            ours = (sim.get(run) or sim.get(RU.norm(run)) or {}).get(key)
            if ours is None:
                continue
            if N == 1:
                # OUTRIGHT STREAM GATED OFF (2026-07-30) on real-price evidence. Backtested on 9
                # majors / 955 priced+rated runners against actual FanDuel+DraftKings CLOSES:
                # the live rule below flagged 528 of 955 runners (55% of the field!) at mean odds
                # 1058, returning 1 winner and -85.6% ROI. The book's fair prices predicted 1.1
                # winners from that set and were almost exactly right; we predicted 3.6. Our
                # longshot probabilities run 1.4-2x the book's across the bottom four quintiles
                # while realized is ~0 — the same over-prediction the top-20 decile curve showed,
                # now confirmed with money prices. Measured overround here is a median 39.5%
                # against ~4.5% on matchups, so this is the worst market for this model on both
                # calibration AND cost. Preview still prints; it just cannot arm.
                if not OUTRIGHT_ARMABLE:
                    pass
                elif ours >= OUT_RATIO * fair and ours * od - 1 >= OUT_EV:
                    preview.append({"stream": "E3-outright", "runner": run, "market": mt,
                                    "odds": od, "edge": round(ours - fair, 3)})
            elif (od >= TN_MIN_ODDS
                  and TN_RATIO_MIN <= ours / max(fair, 1e-9) <= TN_RATIO_MAX
                  and _blend(fair, ours) - fair >= TN_EDGE):
                # gate on the RAW ratio (that is what the 2.0 cap was measured against), but
                # price off the BLEND — what we actually believe once the market is weighted in
                _pb = _blend(fair, ours)
                preview.append({"stream": "E3-top%d" % N, "runner": run, "market": mt[:40],
                                "odds": od, "edge": round(_pb - fair, 3),
                                "p_raw": round(ours, 4), "p_bet": round(_pb, 4),
                                "ev": round(_pb * od - 1.0, 4)})

    # ---- birdies-or-better: MARKET-ANCHORED LEVEL, player-relative edges ----
    # Two corrections after v1 ran +11.3pts hot on every Over (one-sided = model error):
    #  1. PAR MIX. v1 priced every course as par-72 4/10/4. Detroit GC is par 70 (4/12/2),
    #     so v1 invented two par-5s at a 47% birdie rate each. Now uses mix_for(tid):
    #     exact hole counts from our harvest, else the par-total rule (validated 8/8 at
    #     par 72 against real hole counts).
    #  2. COURSE LEVEL IS NOT KNOWABLE PRE-TOURNAMENT. Measured on 15 harvested events,
    #     courses vary 0.78x-1.29x in birdie rate BEYOND their par mix (sd 13%) — larger
    #     than any player edge we could carry. The market CAN see this (course history,
    #     setup, agronomy); we cannot. So we solve one multiplier LAM that makes our
    #     field-average P(over) match the market's, and bet only DEVIATIONS from it.
    #     This is the plan's "mispricing detector, not oracle" made literal: we never
    #     claim to know the course level, only who beats it.
    try:
        import pga_birdies as B
        import re as _re
        brows = [(mkt, mt, run, od) for mkt, mt, run, od in rows
                 if ("BIRDIES" in (mt or "").upper() or "irdie" in (mkt or ""))
                 and od and od > 1.0]
        if brows:
            # CONTEXT (2026-07-29): course factor + wind now enter the RATES themselves,
            # so the market anchor only has to absorb what we genuinely cannot know. Before
            # this the anchor was silently doing the course's whole job.
            _cf, _cn, _wind = 1.0, 0, None
            try:
                import pga_context as C
                _cf, _cn = C.course_factor(evn)
                import pga_e1 as _E1, pga_field as _PF
                _la, _lo = _PF.coords()
                if _la is not None:
                    # MUST be the same statistic fit_wind was built on (mean of DAILY
                    # MAXIMA). Feeding the mean of all hourly values, nights included, put
                    # this ~7.5 km/h below the fitted scale and inflated every birdie rate by
                    # 3.88% in all weather — most of the +4.0pt level bias the devigged audit
                    # found. pga_context owns the definition so the two cannot drift again.
                    _wind = C.live_wind_stat(_la, _lo, days=4)
                print(f"  birdies: course factor {_cf:.3f} ({_cn} prior editions), "
                      f"wind {_wind if _wind is None else round(_wind, 1)} km/h")
            except Exception as _ce:
                print(f"  birdies: context unavailable ({str(_ce)[:40]})")
            # course_name gives rates() this venue's own per-par baseline (the fix
            # that took the reliability slope from 0.617 to 1.059)
            BR, _fr = B.rates(course_factor=_cf, wind_kmh=_wind, course_name=evn)
            BRn = {RU.norm(k): v for k, v in BR.items()}
            try:
                # resolve the ORCHESTRATOR tid from the event name — ESPN ids are a
                # different namespace and silently defaulted every course to par 72.
                _tid = B.tid_for_name(evn)
                _mix = B.mix_for(_tid) if _tid else None
                if _mix:
                    print(f"  birdies: course {_tid} par mix {_mix}")
            except Exception:
                _mix = None
            if not _mix:
                _mix = B.DEFAULT_MIX
            # parse the board once
            parsed = []
            for mkt, mt, run, od in brows:
                pm = _re.match(r"(.+?)\s+Total Birdies or Better", mkt)
                sm = _re.search(r"(Over|Under)\s+([\d.]+)", run)
                if not pm or not sm:
                    continue
                rr = BRn.get(RU.norm(pm.group(1).strip()))
                if not rr:
                    continue
                parsed.append((pm.group(1).strip(), sm.group(1).lower(),
                               float(sm.group(2)), od, mkt, rr))
            overs = [x for x in parsed if x[1] == "over"]
            # DEVIG BEFORE ANCHORING (2026-07-30). The anchor used to target
            # mean(1/odds_over), i.e. the Over price WITH the vig in it. Measured overround on
            # these lines is 6.04%, so that target sat +3.02 points above fair — which forced
            # over-edges to average 0 (they should average -3.02) and under-edges to average
            # -6.04. Unders could then never clear a +5% threshold: the 10-over / 1-under
            # split the audit caught. Worse, every flagged over was over-valued by ~3 points.
            # Pair each player's two quotes and anchor to the FAIR probability instead.
            _q = {}
            for _pl, _sd, _ln, _od, _mk, _rr in parsed:
                _q.setdefault((RU.norm(_pl), _ln), {})[_sd] = _od
            fair_over = {}
            for _k, _v in _q.items():
                if "over" in _v and "under" in _v:
                    _io, _iu = 1.0 / _v["over"], 1.0 / _v["under"]
                    if _io + _iu > 0:
                        fair_over[_k] = _io / (_io + _iu)
            _pairs = [x for x in overs if (RU.norm(x[0]), x[2]) in fair_over]
            if _pairs:
                _rawm = sum(1 / x[3] for x in _pairs) / len(_pairs)
                _fairm = sum(fair_over[(RU.norm(x[0]), x[2])] for x in _pairs) / len(_pairs)
                print("  birdies: devig on %d/%d two-sided lines — raw Over %.4f vs FAIR "
                      "%.4f (vig %.2f pts)"
                      % (len(_pairs), len(overs), _rawm, _fairm, 100 * (_rawm - _fairm)))
            LAM = 1.0
            if len(_pairs) >= 8:
                # bisect LAM so mean model P(over) == mean FAIR P(over)
                overs = _pairs
                tgt = sum(fair_over[(RU.norm(x[0]), x[2])] for x in overs) / len(overs)
                lo, hi = 0.5, 1.6
                for _ in range(28):
                    LAM = (lo + hi) / 2
                    scaled = {p: min(v * LAM, 0.95) for p, v in ()} if False else None
                    m = 0.0
                    for _pl, _sd, ln, _od, _mk, rr in overs:
                        rs = {k: min(v * LAM, 0.95) for k, v in rr.items()}
                        m += B.p_x_or_more(rs, int(ln + 0.5), _mix)
                    m /= len(overs)
                    if m > tgt:
                        hi = LAM
                    else:
                        lo = LAM
                print(f"  birdies: course-level LAM={LAM:.3f} "
                      f"(market-anchored on {len(overs)} Over lines, mix {_mix})")
            # CALIBRATION GATE, separate from G2 (2026-07-30). G2 asks whether the ruler
            # matches the book on matchups; it says nothing about whether birdie TAIL
            # probabilities are calibrated, and they are not — measured reliability slope 0.61
            # against a 0.85 bar. Preview still prints so the numbers stay visible.
            _ok_b, _why_b = B.birdie_stream_armable()
            if not _ok_b:
                print("  birdies: NOT ARMABLE — %s" % _why_b)
            seen_b = set()
            _nb = {"over": 0, "under": 0}
            for player, side, line, od, mkt, rr in parsed:
                rs = {k: min(v * LAM, 0.95) for k, v in rr.items()}
                p_over = B.p_x_or_more(rs, int(line + 0.5), _mix)
                ours = p_over if side == "over" else 1 - p_over
                edge = ours - 1 / od
                key = (RU.norm(player), side, line)
                if (edge >= 0.05 and ours <= B_RATIO_MAX * (1.0 / od)
                        and key not in seen_b):
                    seen_b.add(key)
                    _nb[side] = _nb.get(side, 0) + 1
                    preview.append({"stream": "E3-birdies",
                                    "runner": f"{player} {side} {line:g}",
                                    "armable": _ok_b,
                                    "market": mkt[:60], "odds": od,
                                    "edge": round(edge, 3)})
            # ONE-SIDEDNESS IS A LEVEL ALARM. With a devigged anchor both sides start
            # from the same handicap, so a persistent all-one-way split means the LEVEL is
            # wrong again — which is exactly how the v1 par-72 bug first showed itself.
            print("  birdies: flags %d over / %d under%s"
                  % (_nb.get("over", 0), _nb.get("under", 0),
                     "  <-- ONE-SIDED, recheck the level" if
                     (_nb.get("over", 0) + _nb.get("under", 0)) >= 6 and
                     min(_nb.get("over", 0), _nb.get("under", 0)) == 0 else ""))
    except Exception as _be:
        print(f"  birdie pricing skipped: {str(_be)[:70]}")

    # DEDUPE (2026-07-29): the same underlying market reaches us under several mtypes
    # (TOP_20_FINISH_IMG vs TOP_20_FINISH_(INCL._TIES)) and again from the competition
    # page, so an un-deduped preview showed the same play eight times and crowded out
    # every other stream. Keep the best-edge instance per (stream, runner, line).
    _best = {}
    for _pv in preview:
        _k = (_pv["stream"], RU.norm(_pv["runner"]), _pv.get("odds"))
        if _k not in _best or _pv["edge"] > _best[_k]["edge"]:
            _best[_k] = _pv
    preview = sorted(_best.values(), key=lambda x: -x["edge"])[:15]
    if armed and preview:
        con = sqlite3.connect(PAPER)
        con.execute(E1.DDL)
        for pv in preview:
            key = f"{evn}|{pv['market']}|{pv['runner']}|{pv['stream']}"
            cur = con.execute(
                "INSERT OR IGNORE INTO flags VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL)",
                (key, now, evn, pv["market"], pv["stream"], pv["runner"], "",
                 pv["odds"], pv["edge"], "", ""))
            flags.append(pv) if cur.rowcount else None
        con.commit()
        con.close()
        print(f"  E3 flags logged: {len(flags)}")
    else:
        print(f"  E3 preview rows: {len(preview)} (not logged — gate not passed)")

    # board: fold into pga_board.json via E1's writer, with the preview attached
    E1._write_board(evn)
    try:
        b = json.loads(E1.BOARD.read_text())
        b["e3"] = {"armed": armed, "g2_n": n_g2, "rows": preview[:8]}
        tmp = E1.BOARD.with_suffix(".tmp")
        tmp.write_text(json.dumps(b))
        tmp.replace(E1.BOARD)
    except (OSError, ValueError) as e:
        print(f"  board merge skipped: {e}")


if __name__ == "__main__":
    main()
