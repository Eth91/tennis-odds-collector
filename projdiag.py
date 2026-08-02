"""Why is proj_hit useless, and is the point projection near its floor? Two separate questions.

proj_hit being uncorrelated with winning (+0.017) has three candidate causes, and they need very
different fixes:

  1. RANGE RESTRICTION. Bets only exist when EV = proj_hit * dec - 1 clears a bar, so the flagged
     set is conditioned on proj_hit. Correlation inside a truncated range understates the real
     relationship. If this is the whole story, proj_hit is fine and the metric was wrong.
  2. BIASED MEAN. The projection sits too high, so every probability derived from it is too high.
     Fixable by shifting.
  3. UNDERSTATED VARIANCE. The mean is roughly right but the distribution around it is assumed far
     tighter than reality, pushing probabilities toward the extremes. This produces exactly the
     observed signature — confident predictions that land near a coin flip — and is fixed by
     widening sigma, NOT by shifting the mean.

(2) and (3) look identical on a calibration plot and have opposite remedies, so they are separated
here explicitly: measure the bias, then measure what sigma the model's own probabilities IMPLY and
compare it to the realized error sd.

The second question — can more data help the POINT projection — is the PGA question again. Errors
have a floor set by how much a player's own output varies game to game. Comparing the model against
that floor, and against a dumb season-average baseline, says whether there is room to improve or
whether it is already at the wall.
"""
import math
import sqlite3
import statistics as st
import sys

sys.path.insert(0, ".")


def norm_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def main():
    c = sqlite3.connect("wnba_ledger.sqlite")
    c.row_factory = sqlite3.Row
    cols = [d[1] for d in c.execute("PRAGMA table_info(predictions)")]
    rows = [dict(r) for r in c.execute("SELECT * FROM predictions WHERE graded=1")]
    c.close()
    R = [r for r in rows if r.get("result") in ("over", "under")
         and r.get("actual") is not None and r.get("elev_avg") is not None
         and r.get("proj_hit") is not None and r.get("line") is not None
         and (r.get("side") or "over") == "over"]
    print("graded overs with everything needed: %d\n" % len(R))

    # ---- 1. range restriction? --------------------------------------------------------------
    ph = [r["proj_hit"] for r in R]
    print("=== 1. is proj_hit range-restricted (would fake a zero correlation)? ===")
    print("   proj_hit spread: min %.2f  p25 %.2f  median %.2f  p75 %.2f  max %.2f  sd %.3f"
          % (min(ph), sorted(ph)[len(ph)//4], st.median(ph),
             sorted(ph)[3*len(ph)//4], max(ph), st.pstdev(ph)))
    print("   -> a sd of %.3f over a %.2f-%.2f range is %s to kill a real correlation"
          % (st.pstdev(ph), min(ph), max(ph),
             "too WIDE" if st.pstdev(ph) > 0.05 else "narrow enough"))

    # ---- 2. bias vs variance ----------------------------------------------------------------
    err = [r["actual"] - r["elev_avg"] for r in R]
    bias, sd_real = st.mean(err), st.pstdev(err)
    print("\n=== 2. mean problem or spread problem? ===")
    print("   bias (actual - projection): %+.2f" % bias)
    print("   realized error sd:          %.2f" % sd_real)
    # what sigma does the model's own probability imply? p = P(actual > line) given mean=proj
    implied = []
    for r in R:
        p = min(max(r["proj_hit"], 0.02), 0.98)
        gap = r["elev_avg"] - r["line"]            # how far the projection sits above the line
        z = -norm_cdf_inv(p)                       # p = P(X > line) = 1 - Phi((line-mu)/s)
        if abs(z) < 1e-6:
            continue
        s = gap / z if z else None
        if s and 0.2 < s < 40:
            implied.append(s)
    if implied:
        print("   sigma the model's OWN probabilities imply: median %.2f" % st.median(implied))
        print("   -> reality is %.1fx wider than the model assumes"
              % (sd_real / st.median(implied)) if st.median(implied) else "")
        print("      (a right mean with a too-tight sigma produces exactly 'confident but 50/50')")

    # ---- 3. is the point projection near its floor? ------------------------------------------
    print("\n=== 3. can MORE DATA improve the point projection? ===")
    mae_model = st.mean([abs(e) for e in err])
    base = [abs(r["actual"] - r["season_avg"]) for r in R if r.get("season_avg")]
    print("   model  |miss|: %.2f" % mae_model)
    if base:
        print("   season-average baseline |miss|: %.2f  -> model beats it by %.2f"
              % (st.mean(base), st.mean(base) - mae_model))
    # floor: a player's own game-to-game sd IS the irreducible part
    import wnba_wowy as W
    ps = W.players()
    floors = []
    for r in R[:80]:
        p = r.get("player")
        if p not in ps:
            continue
        try:
            lg = W.game_log(ps[p]["id"])
        except Exception:                                          # noqa: BLE001
            continue
        key = {"points": "pts", "rebounds": "reb", "assists": "ast"}.get(r["stat"])
        if not key:
            continue
        v = [g.get(key) or 0 for g in lg if (g.get("min") or 0) > 0]
        if len(v) >= 6:
            floors.append(st.pstdev(v))
    if floors:
        f = st.mean(floors)
        print("   players' OWN game-to-game sd (the irreducible floor): %.2f" % f)
        print("   implied best-possible |miss| ~ %.2f (0.8 * sd)" % (0.8 * f))
        print("   -> model is at %.2f vs a floor of ~%.2f: %s"
              % (mae_model, 0.8 * f,
                 "AT THE WALL" if mae_model <= 0.8 * f * 1.15 else
                 "%.0f%% of headroom remains" % (100 * (mae_model - 0.8 * f) / mae_model)))


def norm_cdf_inv(p):
    # Acklam approximation, enough for a diagnostic
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    cc = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
          -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph_ = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((cc[0]*q+cc[1])*q+cc[2])*q+cc[3])*q+cc[4])*q+cc[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > ph_:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((cc[0]*q+cc[1])*q+cc[2])*q+cc[3])*q+cc[4])*q+cc[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


if __name__ == "__main__":
    main()
