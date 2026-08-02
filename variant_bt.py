"""Do the sigma widening and the 25/75 blend HURT the bets that actually make money?

The diagnosis came from 114 graded overs. The RECORD comes from the ~52 that survive
current_selection. Those are different universes, and the standing rule here is to judge a change
on the post-selection one, in UNITS, never on MAE over everything flagged.

WHY THIS CANNOT BE A SIMPLE RE-SCORE. Changing the projection changes proj_hit, which changes
EV = proj_hit * dec - 1, which changes WHICH BETS CLEAR THE BAR. So each variant re-runs the EV
gate and re-scores whatever survives, rather than re-pricing a fixed set.

THE ONE-SIDED LIMITATION, stated plainly because it bounds every number below. Only bets the CURRENT
model flagged exist in the ledger. A variant that would have found NEW bets cannot be credited for
them — there is no outcome recorded for a bet never made. So this measures exactly one thing:
does the change damage what we already do? That is precisely the question asked ("don't change a
model that works"), and it is not a claim that the variant is better overall.

SIGMA. The model's own probabilities imply sigma ~3.65 while realized error sd is 6.56. Variants:
  - current      : implied sigma, unchanged
  - wide1.8      : 1.8x, the measured gap
  - per-player   : each player's own game-to-game sd for that stat, the principled version
                   (a single shared sigma corrupts RANKING by construction, since players differ)
BLEND. proj = w * elevated + (1-w) * season_avg, w = 1.00 (current) and 0.25 (measured best).
"""
import math
import sqlite3
import statistics as st
import sys

sys.path.insert(0, ".")
import wnba_wowy as W

OVER_EV_MIN = 0.10
STATKEY = {"points": "pts", "rebounds": "reb", "assists": "ast"}


def _ppf(p):
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    cc = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
          -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((cc[0]*q+cc[1])*q+cc[2])*q+cc[3])*q+cc[4])*q+cc[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > ph:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((cc[0]*q+cc[1])*q+cc[2])*q+cc[3])*q+cc[4])*q+cc[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def p_over(mu, sigma, line):
    if sigma <= 0:
        return 1.0 if mu > line else 0.0
    return 1.0 - 0.5 * (1.0 + math.erf((line - mu) / (sigma * math.sqrt(2.0))))


def main():
    c = sqlite3.connect("wnba_ledger.sqlite")
    c.row_factory = sqlite3.Row
    cols = [d[1] for d in c.execute("PRAGMA table_info(predictions)")]
    allrows = [dict(r) for r in c.execute("SELECT * FROM predictions WHERE graded=1")]
    c.close()
    g = [r for r in allrows if r.get("result") in ("over", "under") and r.get("odds")]
    overs = [r for r in g if str(r.get("side")) == "over"]
    import wnba_slip as S
    sel, _ = S.current_selection(overs, commit=False)
    uni = [r for r in sel if str(r.get("confidence")) in ("confirmed", "likely")
           and r.get("actual") is not None and r.get("elev_avg") is not None
           and r.get("season_avg") and r.get("line") is not None]
    print("SELECTED universe with everything needed: %d\n" % len(uni))

    ps = W.players()
    sig_cache = {}

    def player_sigma(r):
        k = (r["player"], r["stat"], str(r["pred_date"])[:10])
        if k in sig_cache:
            return sig_cache[k]
        out = None
        key = STATKEY.get(r["stat"])
        if key and r["player"] in ps:
            try:
                lg = [x for x in W.game_log(ps[r["player"]]["id"])
                      if str(x.get("date"))[:10] < k[2] and (x.get("min") or 0) > 0]
                v = [x.get(key) or 0 for x in lg]
                if len(v) >= 6:
                    out = st.pstdev(v)
            except Exception:                                     # noqa: BLE001
                out = None
        sig_cache[k] = out
        return out

    def implied_sigma(r):
        p = min(max(r.get("proj_hit") or 0.5, 0.02), 0.98)
        gap = r["elev_avg"] - r["line"]
        z = _ppf(p)
        return abs(gap / z) if abs(z) > 1e-6 else 4.0

    def score(rows, label):
        if not rows:
            print("  %-36s (no bets survive)" % label)
            return
        w = sum(1 for r in rows if r["result"] == r["side"])
        u = sum((float(r["odds"]) - 1.0) if r["result"] == r["side"] else -1.0 for r in rows)
        print("  %-36s %2d-%-2d  hit %5.1f%%  units %+6.2f  ROI %+6.1f%%"
              % (label, w, len(rows) - w, 100.0 * w / len(rows), u, 100.0 * u / len(rows)))

    print("=== BASELINE: what the selected universe actually returned ===")
    score(uni, "  current model (as bet)")

    print("\n=== VARIANTS — re-running the EV>=0.10 gate under each ===")
    for wgt in (1.00, 0.25):
        for mode in ("current", "wide1.8", "per-player"):
            kept = []
            for r in uni:
                mu = wgt * r["elev_avg"] + (1 - wgt) * r["season_avg"]
                base = implied_sigma(r)
                sg = base if mode == "current" else (
                    base * 1.8 if mode == "wide1.8" else (player_sigma(r) or base * 1.8))
                if p_over(mu, sg, float(r["line"])) * float(r["odds"]) - 1.0 >= OVER_EV_MIN:
                    kept.append(r)
            score(kept, "  blend %3.0f%% elev / sigma %s" % (100 * wgt, mode))

    print("\n  NOTE: one-sided. Bets a variant would ADD have no recorded outcome, so keeping")
    print("  fewer bets is not automatically worse — only the UNITS it keeps are evidence.")


if __name__ == "__main__":
    main()
