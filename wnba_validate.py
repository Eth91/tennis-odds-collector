"""Prospective validation of the FROZEN WNBA model (v1.0). Measurement only — never tuning.

WHY THIS EXISTS. The betting logic took 132 commits in 20 days against 151 graded bets — roughly
one logic change per graded bet — and the selection rule alone reversed three times in thirteen
days (sticky 7/17 -> unsticky 7/19 -> sticky-with-margin 7/30). Every change was individually
reasonable and locally justified; collectively that is fitting to last week's noise. Nothing has
ever been measured against a model that stayed still.

So the model is frozen and this file does one job: decide, from PROSPECTIVE evidence alone, whether
it beats the market. Everything below is PRE-REGISTERED — the universe, the hypotheses, the
boundaries and the halts were fixed BEFORE the first prospective bet, on 2026-07-30. Changing any
of them restarts the record.

THE UNIVERSE IS PRE-REGISTERED, AND IT IS NOT THE RAW LEDGER. This matters more here than in golf.
The ledger contains rows that `current_selection` already drops, and profiling it produces false
findings — a "d_min>8 bleeds -8.79u" bucket that turned out to be pre-gate legacy rows the bot
never carded. The universe is therefore:

    graded OVER rows -> wnba_slip.current_selection() -> confidence in {confirmed, likely}

which is exactly what the tracker counts and exactly what the bot now bets.

    H0 : outcomes occur at the DEVIGGED MARKET rate  (two-way: odds vs odds_other)
    H1 : outcomes occur at the MODEL rate            (proj_hit)

    per-bet log-likelihood ratio
        L_i = y*log(p_model/p_fair) + (1-y)*log((1-p_model)/(1-p_fair))

    boundaries at alpha = 0.05, beta = 0.20
        upper  log((1-beta)/alpha) = +2.773  -> reject H0: the edge is real
        lower  log(beta/(1-alpha)) = -1.558  -> accept H0: no edge, HALT

Asymmetric on purpose: ~2.8 nats to believe the edge, ~1.6 to abandon it. Losing money costs more
than missing an edge.

WHY A SEQUENTIAL TEST RATHER THAN ROI. At these odds separating a true edge from zero on ROI alone
needs many hundreds of bets, and the slate produces a handful a night. The SPRT answers the sharper
question — does proj_hit predict outcomes better than the market price? — with no fixed sample size
and no penalty for looking after every slate, which is how it will actually be used.

THE ONE THING THIS TEST IS BUILT TO CATCH. On the 47 graded bets available at freeze time,
`proj_hit` was ANTI-predictive within the selected sample: low third predicted 0.581 -> realised
0.867, high third predicted 0.821 -> realised 0.647. That may be range restriction (we select on
EV, so the surviving spread is narrow and can invert by chance) or it may be real. This SPRT is
precisely the instrument that decides it: if proj_hit is genuinely no better than the price, the
LLR walks to the lower boundary and the model halts itself.

HALT CONDITIONS (any one, immediately, no discretion):
  H-1  SPRT crosses the lower boundary                     -> no edge over the market
  H-2  reliability slope < 0.70 over the trailing 100 bets -> probabilities have drifted
  H-3  n >= 60 and the ROI 95% CI upper bound < 0          -> losing beyond sampling noise
  H-4  the frozen fingerprint changes without a written decision, or the injury feed goes stale

ADOPTION RULE FOR ANY PROPOSED CHANGE. A modification is a HYPOTHESIS. It runs in SHADOW against
the frozen baseline on the same bets and must win a PAIRED SPRT over >= 60 prospective settled bets
before adoption. Retrospective improvement on data the change was designed against counts for
nothing — that is how 132 commits happened.

RETROSPECTIVE ROWS DO NOT COUNT. Everything graded before the freeze was produced by a model that
was changing underneath it. They are reported separately, for context only.
"""
import datetime as dt
import json
import math
import sqlite3
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "wnba_ledger.sqlite"
FREEZE = HERE / "wnba_v1_freeze.json"
REPORT = HERE / "WNBA_EVIDENCE.md"
STATE = HERE / "wnba_evidence.json"

ALPHA, BETA = 0.05, 0.20
UPPER = math.log((1 - BETA) / ALPHA)          # +2.773
LOWER = math.log(BETA / (1 - ALPHA))          # -1.558
MIN_N_ADOPT = 60
SLOPE_HALT, SLOPE_WINDOW = 0.70, 100
FROZEN_ON = "2026-07-31"   # v1.1 — see wnba_v1_freeze.json decision
BET_ROLES = {"confirmed", "likely"}


def _universe():
    """The pre-registered universe: graded overs -> current_selection -> role gate."""
    if not LEDGER.exists():
        return [], []
    con = sqlite3.connect(LEDGER)
    cols = [d[1] for d in con.execute("PRAGMA table_info(predictions)")]
    rows = [dict(zip(cols, r)) for r in con.execute("SELECT * FROM predictions WHERE graded=1")]
    con.close()
    rows = [r for r in rows if r.get("result") in ("over", "under") and r.get("odds")]
    overs = [r for r in rows if (r.get("side") or "over") == "over"]
    try:
        import wnba_slip as S
        sel, _ = S.current_selection(overs, commit=False)
    except Exception:                                          # noqa: BLE001
        sel = overs
    uni = [r for r in sel if str(r.get("confidence")) in BET_ROLES]
    pre = [r for r in uni if str(r.get("pred_date"))[:10] < FROZEN_ON]
    post = [r for r in uni if str(r.get("pred_date"))[:10] >= FROZEN_ON]
    return pre, post


def _fair(r):
    """Devigged market probability for the side we took. None when the other side is missing —
    an un-devigged 1/odds carries the vig and would understate the market, flattering us."""
    o, oth = r.get("odds"), r.get("odds_other")
    if not o or not oth:
        return None
    io_, iu = 1.0 / float(o), 1.0 / float(oth)
    return io_ / (io_ + iu) if (io_ + iu) > 0 else None


def _clip(p):
    return min(max(float(p), 1e-6), 1 - 1e-6)


def metrics(rows):
    sc = [r for r in rows if r.get("proj_hit") is not None and _fair(r) is not None]
    if not sc:
        return None
    y = [1.0 if r["result"] == "over" else 0.0 for r in sc]
    pm = [_clip(r["proj_hit"]) for r in sc]
    pf = [_clip(_fair(r)) for r in sc]
    n = len(sc)
    llr = sum(a * math.log(p / q) + (1 - a) * math.log((1 - p) / (1 - q))
              for a, p, q in zip(y, pm, pf))

    def ll(ps):
        return -sum(a * math.log(p) + (1 - a) * math.log(1 - p) for a, p in zip(y, ps)) / n

    def brier(ps):
        return sum((p - a) ** 2 for a, p in zip(y, ps)) / n

    nb = max(2, min(5, n // 8))
    idx = sorted(range(n), key=lambda i: pm[i])
    xs, ys = [], []
    per = max(1, n // nb)
    for b in range(nb):
        ix = idx[b * per:(b + 1) * per] if b < nb - 1 else idx[b * per:]
        if ix:
            xs.append(st.mean(pm[i] for i in ix))
            ys.append(st.mean(y[i] for i in ix))
    slope = None
    if len(xs) >= 2:
        mx, my = st.mean(xs), st.mean(ys)
        den = sum((x - mx) ** 2 for x in xs)
        if den > 0:
            slope = sum((x - mx) * (yy - my) for x, yy in zip(xs, ys)) / den
    rets = [(float(r["odds"]) - 1) if r["result"] == "over" else -1.0 for r in rows]
    pnl, tn = sum(rets), len(rets)
    roi = pnl / tn if tn else 0.0
    se = (st.pstdev(rets) / math.sqrt(tn)) if tn > 1 else None
    be = sum(1 / float(r["odds"]) for r in rows) / tn
    return {"n_scored": n, "n_settled": tn, "wins": int(sum(y)), "losses": int(n - sum(y)),
            "llr": llr, "logloss_model": ll(pm), "logloss_market": ll(pf),
            "brier_model": brier(pm), "brier_market": brier(pf), "slope": slope,
            "pnl": pnl, "roi": roi, "breakeven": be,
            "roi_ci": (roi - 1.96 * se, roi + 1.96 * se) if se else None,
            "exp_model": sum(pm), "exp_market": sum(pf), "actual": sum(y)}


def verdict(m):
    if m is None:
        return "INSUFFICIENT DATA", ["no prospective settled bets yet"]
    notes, v = [], "CONTINUE COLLECTING"
    if m["llr"] >= UPPER:
        v = "H0 REJECTED — the model beats the market at the pre-registered boundary"
        notes.append(f"LLR {m['llr']:+.3f} crossed +{UPPER:.3f}")
    elif m["llr"] <= LOWER:
        v = "HALT (H-1) — accept H0: no edge over the devigged market"
        notes.append(f"LLR {m['llr']:+.3f} crossed {LOWER:.3f}")
    else:
        notes.append(f"LLR {m['llr']:+.3f} inside ({LOWER:.3f}, +{UPPER:.3f}) — undecided")
    if m["slope"] is not None and m["n_scored"] >= SLOPE_WINDOW and m["slope"] < SLOPE_HALT:
        v = "HALT (H-2) — reliability slope below the floor"
        notes.append(f"slope {m['slope']:.3f} < {SLOPE_HALT}")
    if m["roi_ci"] and m["n_scored"] >= MIN_N_ADOPT and m["roi_ci"][1] < 0:
        v = "HALT (H-3) — losing beyond sampling noise"
        notes.append(f"ROI 95% CI upper {m['roi_ci'][1]:+.3f} < 0")
    return v, notes


def _block(title, m, note=""):
    L = [f"## {title}", ""]
    if m is None:
        L += ["_none yet_", ""]
        return L
    ci = m["roi_ci"]
    L += [f"{note}" if note else "", "",
          "| metric | model | market |", "|---|---|---|",
          f"| log loss | **{m['logloss_model']:.5f}** | {m['logloss_market']:.5f} |",
          f"| Brier | **{m['brier_model']:.5f}** | {m['brier_market']:.5f} |",
          f"| expected wins | {m['exp_model']:.1f} | {m['exp_market']:.1f} |",
          f"| actual wins | {m['actual']:.0f} | |", "",
          "| | |", "|---|---|",
          f"| settled / scored | {m['n_settled']} / {m['n_scored']} |",
          f"| record | {m['wins']}-{m['losses']} |",
          f"| P&L (1u flat) | {m['pnl']:+.2f}u |",
          f"| ROI vs breakeven | {100*m['roi']:+.2f}% vs {100*m['breakeven']:.1f}% |",
          (f"| ROI 95% CI | {100*ci[0]:+.2f}% .. {100*ci[1]:+.2f}% |" if ci else "| ROI 95% CI | n/a |"),
          (f"| reliability slope | {m['slope']:.3f} |" if m["slope"] is not None
           else "| reliability slope | n/a |"),
          f"| **SPRT log-likelihood ratio** | **{m['llr']:+.4f}** |", ""]
    return L


def report():
    pre, post = _universe()
    mp, mo = metrics(post), metrics(pre)
    v, notes = verdict(mp)
    ts = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    try:
        fz = json.loads(FREEZE.read_text())
        fid = f"constants `{fz['sha256_16']}` · source `{fz['source_sha256_16']}`"
    except Exception:                                          # noqa: BLE001
        fid = "_fingerprint unreadable_"
    try:
        _ver = json.loads(FREEZE.read_text()).get("version", "v?")
    except Exception:                                          # noqa: BLE001
        _ver = "v?"
    L = [f"# WNBA {_ver} — cumulative evidence", "",
         f"_updated {ts} · frozen {FROZEN_ON} · {fid}_", "",
         "_measurement only; this file never tunes the model_", "",
         "## Verdict", "", f"**{v}**", ""]
    L += [f"- {n}" for n in notes]
    L += ["", f"## Pre-registered test (fixed {FROZEN_ON}, before any prospective bet)", "",
          "| | |", "|---|---|",
          "| universe | graded overs → `current_selection` → confidence ∈ {confirmed, likely} |",
          "| H0 | outcomes at the DEVIGGED market rate (odds vs odds_other) |",
          "| H1 | outcomes at the model rate (`proj_hit`) |",
          f"| boundaries | reject H0 at LLR ≥ +{UPPER:.3f}; accept H0 at LLR ≤ {LOWER:.3f} |",
          f"| halts | H-1 lower boundary · H-2 slope < {SLOPE_HALT} over {SLOPE_WINDOW} "
          f"· H-3 n≥{MIN_N_ADOPT} and ROI CI upper < 0 · H-4 fingerprint drift / stale feed |",
          f"| adoption | a challenger must win a PAIRED SPRT over ≥ {MIN_N_ADOPT} "
          "PROSPECTIVE settled bets |", ""]
    L += _block("Prospective record (this is the test)", mp,
                "Bets carded on or after the freeze date.")
    L += _block("Retrospective, for context only — NOT part of the test", mo,
                "Produced by a model that was changing underneath it (132 commits / 151 bets). "
                "Reported so the freeze has a baseline, never as evidence.")
    L += ["## Standing instruction", "",
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
          "  **FIRST TEST ON OUR OWN BETS (2026-07-31) — it does NOT transfer.** Refitting DvP as-of each bet's own date and applying the filter to the counted record makes it worse at EVERY threshold: drop coef<=-0.005 -> 20-14 / +4.53u (-14 bets, -14.52u); <=-0.010 -> 29-15 / +13.43u (-5.62u); <=-0.015 -> -4.54u; <=-0.020 -> -1.26u, against a 33-15 / +19.05u baseline. The split is REVERSED here: our overs into a TOUGH positional defence went 4-0 (+5.62u) where the backtest's universe gave 45.2%. Plausible mechanism: the backtest scores general props, while our bets are injury-beneficiary overs whose minutes and usage are exploding — role expansion dominates matchup, so a tough defence costs far less than it does for an ordinary prop. ⚠ n=4 in that bucket proves nothing on its own; it merely fails to confirm. Also 17 of 48 bets could not be resolved to a position/opponent and went 9-8 (52.9%), worse than the resolved ones — worth its own look. CONCLUSION: do not gate on DvP; keep it as the tiebreaker it is, and let the prospective record settle it.",
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
          "resolve this by argument — it is why both are registered.", ""]
    REPORT.write_text("\n".join(L), encoding="utf-8")
    STATE.write_text(json.dumps({"updated": ts, "frozen": FROZEN_ON, "verdict": v,
                                 "prospective": mp, "retrospective": mo}, indent=1),
                     encoding="utf-8")
    print("\n".join(L))
    return mp


if __name__ == "__main__":
    report()
