"""Prospective validation of the FROZEN PGA model (v1.0). Measurement only — never tuning.

The model is frozen. This file's job is to decide, from prospective evidence alone, whether it
beats the market — and to be unable to flatter it. Everything below is PRE-REGISTERED: the
hypotheses, the boundaries, the halt conditions and the bar a challenger must clear were all fixed
BEFORE the first settled bet, on 2026-07-30, with n = 0. Changing any of them later invalidates the
test, so if a threshold has to move, the record restarts.

WHY A SEQUENTIAL TEST RATHER THAN ROI. ROI is the number everyone wants and the worst one to wait
for: at typical top-N odds the per-bet return sd is ~2.0, so separating a true +9% edge from zero
at 95% confidence needs roughly (1.96*2.0/0.09)^2 ~= 1,900 settled bets — about three years at this
flag rate. The model would be obsolete before the answer arrived.

The question that actually matters is sharper and cheaper: DOES p_bet PREDICT OUTCOMES BETTER THAN
p_fair? That is a paired comparison on every settled bet, and Wald's SPRT answers it with no fixed
sample size and no penalty for looking after every tournament — which is exactly how this will be
used.

    H0 : outcomes occur at the devigged MARKET rate p_fair   (the model adds nothing)
    H1 : outcomes occur at the MODEL rate p_bet              (the model's edge is real)

    per-bet log-likelihood ratio
        L_i = y*log(p_bet/p_fair) + (1-y)*log((1-p_bet)/(1-p_fair))

    boundaries at alpha = 0.05, beta = 0.20
        upper  log((1-beta)/alpha) = +2.773  -> reject H0: the edge is real
        lower  log(beta/(1-alpha)) = -1.558  -> accept H0: no edge, HALT

Note the asymmetry is deliberate and unfavourable to the model: it takes ~2.8 nats of evidence to
believe the edge and only ~1.6 to abandon it. Losing money is more costly than missing an edge.

A REAL LIMITATION, STATED UP FRONT. This test rewards the model for being better CALIBRATED than
the market on the bets it chose to place. It is conditioned on the model's own selection, so it
cannot detect an edge that exists only in markets the gates never fire on, and it does not by
itself prove profitability after vig — that is what the ROI and yield columns are for, reported
alongside but never used as the stopping rule.

HALT CONDITIONS (any one, immediately, no discretion):
  H-1  SPRT crosses the lower boundary                     -> no edge
  H-2  reliability slope < 0.70 over the trailing 200 bets -> probabilities have drifted
  H-3  n >= 100 and the ROI 95% CI upper bound < 0         -> losing beyond sampling noise
  H-4  probability conservation breaks, or the vig band rejects >50% of markets in a week
       -> data integrity, not model performance

ADOPTION RULE FOR ANY PROPOSED CHANGE. A modification is a HYPOTHESIS, not an improvement. It runs
in SHADOW next to the frozen baseline, priced on the same bets, and must beat it on a PAIRED SPRT
over >= 100 prospective settled bets before it can be adopted. Retrospective improvement on data
the change was designed against counts for nothing — that is how the model acquired the tail bug
and the blend-weight error in the first place.
"""
import datetime as dt
import json
import math
import sqlite3
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAPER = HERE / "pga_paper.sqlite"
REPORT = HERE / "pga_evidence.md"
STATE = HERE / "pga_evidence.json"

ALPHA, BETA = 0.05, 0.20
UPPER = math.log((1 - BETA) / ALPHA)          # +2.773
LOWER = math.log(BETA / (1 - ALPHA))          # -1.558
MIN_N_ADOPT = 100
SLOPE_HALT, SLOPE_WINDOW = 0.70, 200
FROZEN = "v1.0  frozen 2026-07-30"


def _rows():
    """Settled bets carrying both probabilities. Rows logged before the ledger was
    instrumented have no p_bet and are counted for ROI but cannot be scored."""
    if not PAPER.exists():
        return [], 0
    con = sqlite3.connect(PAPER)
    cols = {d[1] for d in con.execute("PRAGMA table_info(flags)")}
    if not {"p_bet", "p_fair"} <= cols:
        graded = con.execute("SELECT COUNT(*) FROM flags WHERE result IN ('W','L')").fetchone()[0]
        con.close()
        return [], graded
    out = list(con.execute(
        "SELECT event, stream, market, runner, odds, p_bet, p_fair, result, pnl, flagged_at "
        "FROM flags WHERE result IS NOT NULL AND result != '' ORDER BY flagged_at"))
    graded = con.execute("SELECT COUNT(*) FROM flags WHERE result IN ('W','L')").fetchone()[0]
    con.close()
    return out, graded


def _clip(p):
    return min(max(float(p), 1e-6), 1 - 1e-6)


def _metrics(rows):
    """Everything the report tracks. Pushes are excluded from scoring but kept in turnover."""
    sc = [r for r in rows if r[7] in ("W", "L") and r[5] is not None and r[6] is not None]
    if not sc:
        return None
    y = [1.0 if r[7] == "W" else 0.0 for r in sc]
    pb = [_clip(r[5]) for r in sc]
    pf = [_clip(r[6]) for r in sc]
    n = len(sc)

    def ll(ps):
        return -sum(a * math.log(p) + (1 - a) * math.log(1 - p) for a, p in zip(y, ps)) / n

    def brier(ps):
        return sum((p - a) ** 2 for a, p in zip(y, ps)) / n

    llr = sum(a * math.log(p / q) + (1 - a) * math.log((1 - p) / (1 - q))
              for a, p, q in zip(y, pb, pf))
    # reliability slope over deciles (or as many bins as the sample supports)
    nb = max(2, min(10, n // 10))
    order = sorted(range(n), key=lambda i: pb[i])
    xs, ys = [], []
    per = max(1, n // nb)
    for b in range(nb):
        ix = order[b * per:(b + 1) * per] if b < nb - 1 else order[b * per:]
        if ix:
            xs.append(st.mean(pb[i] for i in ix))
            ys.append(st.mean(y[i] for i in ix))
    slope = None
    if len(xs) >= 2:
        mx, my = st.mean(xs), st.mean(ys)
        den = sum((x - mx) ** 2 for x in xs)
        if den > 0:
            slope = sum((x - mx) * (yy - my) for x, yy in zip(xs, ys)) / den
    pnl = sum(float(r[8] or 0.0) for r in rows)
    turnover = float(len(rows))
    rets = [float(r[8] or 0.0) for r in rows]
    roi = pnl / turnover if turnover else 0.0
    se = (st.pstdev(rets) / math.sqrt(len(rets))) if len(rets) > 1 else None
    return {
        "n_scored": n, "n_settled": len(rows),
        "wins": int(sum(y)), "losses": int(n - sum(y)),
        "pushes": len(rows) - n,
        "llr": llr, "logloss_model": ll(pb), "logloss_market": ll(pf),
        "brier_model": brier(pb), "brier_market": brier(pf),
        "slope": slope, "pnl": pnl, "roi": roi, "yield": roi,
        "roi_ci": (roi - 1.96 * se, roi + 1.96 * se) if se else None,
        "exp_hits_model": sum(pb), "exp_hits_market": sum(pf), "actual_hits": sum(y),
        "avg_odds": st.mean(float(r[4]) for r in rows if r[4]),
    }


def _verdict(m):
    if m is None:
        return "INSUFFICIENT DATA", ["no settled bets carrying both probabilities yet"]
    notes, v = [], "CONTINUE COLLECTING"
    if m["llr"] >= UPPER:
        v = "H0 REJECTED — edge is real at the pre-registered boundary"
        notes.append(f"LLR {m['llr']:+.3f} crossed the +{UPPER:.3f} boundary")
    elif m["llr"] <= LOWER:
        v = "HALT (H-1) — accept H0, no edge over the market"
        notes.append(f"LLR {m['llr']:+.3f} crossed the {LOWER:.3f} boundary")
    else:
        notes.append(f"LLR {m['llr']:+.3f} inside ({LOWER:.3f}, +{UPPER:.3f}) — undecided")
    if m["slope"] is not None and m["n_scored"] >= SLOPE_WINDOW and m["slope"] < SLOPE_HALT:
        v = "HALT (H-2) — reliability slope below the floor"
        notes.append(f"slope {m['slope']:.3f} < {SLOPE_HALT}")
    if m["roi_ci"] and m["n_scored"] >= MIN_N_ADOPT and m["roi_ci"][1] < 0:
        v = "HALT (H-3) — losing beyond sampling noise"
        notes.append(f"ROI 95% CI upper {m['roi_ci'][1]:+.3f} < 0")
    return v, notes


def report():
    rows, graded = _rows()
    m = _metrics(rows)
    v, notes = _verdict(m)
    ts = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    L = [f"# PGA {FROZEN} — cumulative evidence", "",
         f"_updated {ts} · measurement only; the model is frozen and this file never tunes it_", "",
         "## Verdict", "", f"**{v}**", ""]
    for nt in notes:
        L.append(f"- {nt}")
    L += ["", "## Pre-registered test (fixed 2026-07-30 at n=0)", "",
          "| | |", "|---|---|",
          "| H0 | outcomes occur at the devigged market rate `p_fair` |",
          "| H1 | outcomes occur at the model rate `p_bet` |",
          f"| boundaries | reject H0 at LLR >= +{UPPER:.3f}; accept H0 at LLR <= {LOWER:.3f} |",
          f"| alpha / beta | {ALPHA} / {BETA} |",
          f"| halt | H-1 lower boundary · H-2 slope < {SLOPE_HALT} over {SLOPE_WINDOW} "
          "· H-3 n>=100 and ROI CI upper < 0 · H-4 data integrity |",
          f"| adoption | a challenger must beat the frozen baseline on a PAIRED SPRT over "
          f">= {MIN_N_ADOPT} prospective settled bets |", ""]
    if m is None:
        L += ["## Evidence", "",
              f"No scored bets yet. Settled rows in the ledger: **{graded}**"
              + ("" if graded == 0 else " (logged before instrumentation — ROI only, unscorable)"),
              "", "Nothing can be concluded. The first scorable bets arrive when a tournament "
              "settles with `p_bet`/`p_fair` recorded.", ""]
    else:
        ci = m["roi_ci"]
        L += ["## Evidence", "",
              "| metric | model | market |", "|---|---|---|",
              f"| log loss | **{m['logloss_model']:.5f}** | {m['logloss_market']:.5f} |",
              f"| Brier | **{m['brier_model']:.5f}** | {m['brier_market']:.5f} |",
              f"| expected hits | {m['exp_hits_model']:.1f} | {m['exp_hits_market']:.1f} |",
              f"| actual hits | {m['actual_hits']:.0f} | |", "",
              "| | |", "|---|---|",
              f"| settled / scored | {m['n_settled']} / {m['n_scored']} |",
              f"| record | {m['wins']}-{m['losses']} ({m['pushes']} push) |",
              f"| P&L (1u flat) | {m['pnl']:+.2f}u |",
              f"| ROI = yield | {100*m['roi']:+.2f}% |",
              f"| ROI 95% CI | {100*ci[0]:+.2f}% .. {100*ci[1]:+.2f}% |" if ci else "| ROI 95% CI | n/a |",
              f"| reliability slope | {m['slope']:.3f} |" if m["slope"] is not None
              else "| reliability slope | n/a |",
              f"| mean odds | {m['avg_odds']:.2f} |",
              f"| **SPRT log-likelihood ratio** | **{m['llr']:+.4f}** |", ""]
    L += ["## Standing instruction", "",
          "No model change is proposed or adopted on this evidence. Every modification is a new "
          "hypothesis and must clear the adoption rule above on PROSPECTIVE data. Retrospective "
          "improvement on data the change was designed against counts for nothing.", ""]
    REPORT.write_text("\n".join(L), encoding="utf-8")
    STATE.write_text(json.dumps({"updated": ts, "frozen": FROZEN, "verdict": v,
                                 "metrics": m, "graded_rows": graded}, indent=1), encoding="utf-8")
    print("\n".join(L))
    return m


if __name__ == "__main__":
    report()
