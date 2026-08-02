"""⛳ pga_calib — MEASURE the constants the model has been assuming.

Seven numbers were hand-set and never fitted. The 2026-07-29 wind refit showed why that
matters: on 7x the data the coefficient shrank 32%, i.e. the small-n fit read hot. These
constants were never fitted at ALL, so they have no n to be small.

Six of the seven are shrinkage strengths, and shrinkage has a closed-form answer — the
empirical-Bayes optimum is k = (noise variance) / (between-unit true variance). Both sides
are measurable, so those six need no tuning and cannot leak: they are estimated on the whole
history and are not chosen to make any scoreboard look good.

RHO is likewise a direct measurement: a nested ANOVA on a player's rounds within versus
across events gives the share of round variance that is player-week form.

Only HALF_LIFE_D is a genuine predictive hyperparameter, so it is the only one tuned — on
2024-25 events ONLY, with 2026 held out for the final read. That keeps the walk-forward an
honest out-of-sample number rather than something we fitted to.

A negative estimated between-unit variance is not an error: it means the observed spread is
no larger than sampling noise predicts, i.e. the effect is indistinguishable from zero. That
is reported as such, and the shrinkage goes to infinity (the term is switched off) rather
than being quietly floored.
"""
import datetime as dt
import math
import sqlite3
import statistics as st
from collections import defaultdict

import pga_ruler as RU

DB = RU.DB
MIN_FIELD = 20          # a round needs this many scores for its field mean to mean anything


# --------------------------------------------------------------- shared residuals
def residuals(min_field=MIN_FIELD):
    """[(player, event_id, date, rnd, rel)] where rel = score - that round's field mean."""
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT event_id, date, player, rnd, score FROM rounds "
                       "WHERE score > 0").fetchall()
    con.close()
    by = defaultdict(list)
    for eid, date, pl, rnd, sc in rows:
        by[(eid, rnd)].append(sc)
    fm = {k: st.mean(v) for k, v in by.items() if len(v) >= min_field}
    out = []
    for eid, date, pl, rnd, sc in rows:
        m = fm.get((eid, rnd))
        if m is not None:
            out.append((RU.norm(pl), eid, date, rnd, sc - m))
    return out


def _eb(noise_var, obs_between_var, mean_inv_n, label, unit="obs"):
    """Empirical-Bayes shrinkage constant k = noise_var / true_between_var.

    obs_between_var is the observed spread of unit estimates, which is inflated by sampling
    noise; subtracting noise_var * mean(1/n) removes that inflation. If what remains is <= 0
    the effect is indistinguishable from zero and k is infinite (term off).
    """
    true_var = obs_between_var - noise_var * mean_inv_n
    if true_var <= 0:
        print("     %s: observed spread %.4f <= sampling noise %.4f -> TRUE VARIANCE ~0, "
              "effect indistinguishable from zero" % (label, obs_between_var,
                                                      noise_var * mean_inv_n))
        return float("inf"), true_var
    k = noise_var / true_var
    print("     %s: noise var %.4f, true between-unit var %.4f -> k = %.1f %s"
          % (label, noise_var, true_var, k, unit))
    return k, true_var


# ------------------------------------------------------------------------- RHO
def fit_rho(verbose=True):
    """Share of a player's round variance that is player-WEEK form rather than per-round.

    Model: rel = mu_player + week_(player,event) + eps_round. A nested ANOVA separates them:
    within an event, only eps varies; across events for one player, week and eps/n both do.
    RHO drives how strongly a player's four rounds move together, which is what makes
    tournament outcomes (cut, top-N) correlated rather than four independent draws.
    """
    res = residuals()
    grp = defaultdict(list)
    for pl, eid, _d, _r, rel in res:
        grp[(pl, eid)].append(rel)
    # eps: pooled within (player, event) variance
    num = den = 0.0
    nrounds = []
    for _k, v in grp.items():
        if len(v) >= 2:
            num += st.variance(v) * (len(v) - 1)
            den += len(v) - 1
            nrounds.append(len(v))
    if den < 100:
        return None
    var_eps = num / den
    nbar = st.mean(nrounds)
    # week: spread of event means around the player's own mean
    by_pl = defaultdict(list)
    for (pl, _eid), v in grp.items():
        if len(v) >= 2:
            by_pl[pl].append(st.mean(v))
    num2 = den2 = 0.0
    for _pl, ms in by_pl.items():
        if len(ms) >= 2:
            num2 += st.variance(ms) * (len(ms) - 1)
            den2 += len(ms) - 1
    if den2 < 50:
        return None
    var_evmean = num2 / den2
    var_week = var_evmean - var_eps / nbar
    rho = var_week / (var_week + var_eps) if var_week > 0 else 0.0
    if verbose:
        print("  RHO (player-week share of round variance)")
        print("     within-event round var (eps)   %.4f   over %d dof" % (var_eps, den))
        print("     event-mean var within player   %.4f   (%.2f rounds/event avg)"
              % (var_evmean, nbar))
        print("     => week var %.4f  -> RHO = %.3f   (current default %.2f)"
              % (var_week, rho, RU.RHO))
    return {"rho": rho, "var_eps": var_eps, "var_week": var_week, "dof": den}


# --------------------------------------------------------------- K_SHRINK / SIG
def fit_k_shrink(verbose=True):
    """EB shrinkage of a player's rating toward the field, in pseudo-rounds."""
    res = residuals()
    by = defaultdict(list)
    for pl, _e, _d, _r, rel in res:
        by[pl].append(rel)
    num = den = 0.0
    means, invn = [], []
    for _pl, v in by.items():
        if len(v) >= 8:
            num += st.variance(v) * (len(v) - 1)
            den += len(v) - 1
            means.append(st.mean(v))
            invn.append(1.0 / len(v))
    if den < 100 or len(means) < 30:
        return None
    var_noise = num / den
    if verbose:
        print("  K_SHRINK (rating shrinkage toward field average)")
    k, tv = _eb(var_noise, st.pvariance(means), st.mean(invn), "rating", "pseudo-rounds")
    if verbose:
        print("     current default %.1f" % RU.K_SHRINK)
    return {"k": k, "var_noise": var_noise, "var_true": tv, "n_players": len(means)}


def fit_sig_shrink(verbose=True):
    """EB shrinkage of a player's own sd toward the global sd.

    A sample sd from n rounds has variance about sigma^2/(2n), so the per-observation noise
    on an sd estimate is sigma^2/2 — that is the numerator for the same k = noise/between
    formula, expressed in rounds.
    """
    res = residuals()
    by = defaultdict(list)
    for pl, _e, _d, _r, rel in res:
        by[pl].append(rel)
    sds, invn, var_all = [], [], []
    for _pl, v in by.items():
        if len(v) >= 15:
            sd = st.stdev(v)
            sds.append(sd)
            invn.append(1.0 / len(v))
            var_all.append(sd * sd)
    if len(sds) < 30:
        return None
    sig2 = st.mean(var_all)
    noise_per_obs = sig2 / 2.0
    if verbose:
        print("  SIG_SHRINK (player sd shrinkage toward global sd)")
    k, tv = _eb(noise_per_obs, st.pvariance(sds), st.mean(invn), "player sd", "rounds")
    if verbose:
        print("     mean player sd %.3f, spread of sds %.4f, current default %.1f"
              % (st.mean(sds), st.pvariance(sds), RU.SIG_SHRINK))
    return {"k": k, "var_true": tv, "n_players": len(sds)}


# --------------------------------------------------------------------- K_FIT
def fit_k_fit(verbose=True):
    """EB shrinkage on PERSONAL COURSE FIT — does a player-course affinity exist at all?

    Course history is the most over-claimed edge in golf, so the interesting output is not
    the shrinkage constant but whether the true between-player-course variance is even
    positive once sampling noise is removed. If it is not, course fit is noise and belongs
    switched off rather than shrunk.
    """
    res = residuals()
    con = sqlite3.connect(DB)
    evname = dict(con.execute("SELECT event_id, event FROM rounds GROUP BY event_id"))
    con.close()
    pl_all = defaultdict(list)
    for pl, _e, _d, _r, rel in res:
        pl_all[pl].append(rel)
    base = {pl: st.mean(v) for pl, v in pl_all.items() if len(v) >= 15}
    # a player's rounds at one COURSE (event name, all editions)
    pc = defaultdict(list)
    for pl, eid, _d, _r, rel in res:
        if pl in base:
            pc[(pl, str(evname.get(eid, "")).lower())].append(rel)
    num = den = 0.0
    devs, invn = [], []
    for (pl, _c), v in pc.items():
        if len(v) >= 4:
            num += st.variance(v) * (len(v) - 1)
            den += len(v) - 1
            devs.append(st.mean(v) - base[pl])
            invn.append(1.0 / len(v))
    if den < 100 or len(devs) < 50:
        return None
    var_round = num / den
    if verbose:
        print("  K_FIT (personal course fit)")
    k, tv = _eb(var_round, st.pvariance(devs), st.mean(invn), "course fit", "pseudo-rounds")
    if verbose:
        print("     %d player-course cells with >=4 rounds, current default %.1f"
              % (len(devs), 8.0))
    return {"k": k, "var_true": tv, "n_cells": len(devs)}


# ------------------------------------------------------------------ K_COURSE
def fit_k_course(verbose=True):
    """EB shrinkage on the COURSE birdie factor, in pseudo-editions."""
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT tid, tname, SUM(p3h), SUM(p3b), SUM(p4h), SUM(p4b), SUM(p5h), SUM(p5b) "
        "FROM birdie_rounds GROUP BY tid").fetchall()
    con.close()
    tot = defaultdict(lambda: [0.0, 0.0])
    for _t, _n, a3, b3, a4, b4, a5, b5 in rows:
        for par, (h, b) in ((3, (a3, b3)), (4, (a4, b4)), (5, (a5, b5))):
            tot[par][0] += h or 0
            tot[par][1] += b or 0
    g = {p: (v[1] / v[0] if v[0] else .15) for p, v in tot.items()}
    # one factor per edition, grouped by course (token-normalised event name)
    by_course = defaultdict(list)
    for _t, tname, a3, b3, a4, b4, a5, b5 in rows:
        h = (a3 or 0) + (a4 or 0) + (a5 or 0)
        if not h:
            continue
        exp = (a3 or 0) * g[3] + (a4 or 0) * g[4] + (a5 or 0) * g[5]
        if exp <= 0:
            continue
        obs = (b3 or 0) + (b4 or 0) + (b5 or 0)
        key = " ".join(sorted(w for w in str(tname or "").lower().split() if len(w) > 3))
        by_course[key].append(obs / exp)
    num = den = 0.0
    means, invn = [], []
    for _c, v in by_course.items():
        if len(v) >= 2:
            num += st.variance(v) * (len(v) - 1)
            den += len(v) - 1
            means.append(st.mean(v))
            invn.append(1.0 / len(v))
    if den < 5 or len(means) < 10:
        if verbose:
            print("  K_COURSE: only %d multi-edition courses -> keeping default" % len(means))
        return None
    var_ed = num / den
    if verbose:
        print("  K_COURSE (course birdie factor)")
    k, tv = _eb(var_ed, st.pvariance(means), st.mean(invn), "course factor",
                "pseudo-editions")
    if verbose:
        print("     %d courses with >=2 editions, current default 2.0" % len(means))
    return {"k": k, "var_true": tv, "n_courses": len(means)}


# ---------------------------------------------------------------------- K_H
def fit_k_h(verbose=True):
    """EB shrinkage on a player's BIRDIE RATE, in pseudo-holes, per par class.

    Noise here is binomial, p(1-p) per hole, so the shrinkage is p(1-p)/var_true_between.
    """
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT player, SUM(p3h), SUM(p3b), SUM(p4h), SUM(p4b), SUM(p5h), SUM(p5b) "
        "FROM birdie_rounds GROUP BY player").fetchall()
    con.close()
    out = {}
    if verbose:
        print("  K_H (player birdie-rate shrinkage, pseudo-holes)")
    for par, hi, bi in ((3, 1, 2), (4, 3, 4), (5, 5, 6)):
        ps, invn = [], []
        th = tb = 0.0
        for r in rows:
            h, b = r[hi] or 0, r[bi] or 0
            th += h
            tb += b
            if h >= 40:
                ps.append(b / h)
                invn.append(1.0 / h)
        if len(ps) < 30:
            continue
        p = tb / th if th else .15
        noise = p * (1 - p)
        k, tv = _eb(noise, st.pvariance(ps), st.mean(invn), "par %d (field p=%.3f)"
                    % (par, p), "pseudo-holes")
        out[par] = k
    if verbose and out:
        print("     current default K_H = 60.0 for all pars")
    return out


# ------------------------------------------------------------- HALF_LIFE (tuned)
def tune_half_life(grid=(45, 60, 90, 120, 180, 270, 365, 100000), tune_seasons=(2024, 2025),
                   verbose=True):
    """The ONLY tuned constant. Searched on 2024-25 events with 2026 HELD OUT, so the 2026
    walk-forward stays an honest out-of-sample read rather than something we fitted."""
    rows = RU.all_rows()
    best = None
    res = []
    if verbose:
        print("  HALF_LIFE_D grid on %s events (2026 held out)" % str(tune_seasons))
    for hl in grid:
        acc, rmse, n = RU.walk_forward(seasons=tune_seasons, season_max=max(tune_seasons),
                                       verbose=False, rows=rows, half_life=float(hl))
        res.append((hl, acc, rmse, n))
        if verbose:
            print("     half-life %6s d: accuracy %.4f  RMSE %.4f  (n=%d)"
                  % ("never" if hl > 9999 else hl, acc, rmse, n))
        if best is None or acc > best[1]:
            best = (hl, acc, rmse, n)
    if verbose:
        print("     BEST on tune set: %s days (accuracy %.4f); current default %.0f"
              % ("no decay" if best[0] > 9999 else best[0], best[1], RU.HALF_LIFE_D))
    return {"best": best[0], "curve": res}


# ------------------------------------------------------------------- par mix
def validate_par_mix(verbose=True):
    """Re-check the par->hole-mix rule on the expanded harvest (it was set on 8 and 5 events)."""
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT tid, tname, SUM(p3h), SUM(p4h), SUM(p5h), COUNT(*) FROM birdie_rounds "
        "GROUP BY tid").fetchall()
    con.close()
    tally = defaultdict(lambda: defaultdict(int))
    for _t, _n, a3, a4, a5, nr in rows:
        if not nr:
            continue
        h3, h4, h5 = round((a3 or 0) / nr), round((a4 or 0) / nr), round((a5 or 0) / nr)
        tot = h3 + h4 + h5
        if tot != 18:
            continue
        par = 3 * h3 + 4 * h4 + 5 * h5
        tally[par][(h3, h4, h5)] += 1
    if verbose:
        print("  PAR MIX RULE re-validation (was set on 8 and 5 events)")
    out = {}
    for par in sorted(tally):
        items = sorted(tally[par].items(), key=lambda kv: -kv[1])
        n = sum(v for _k, v in items)
        top, cnt = items[0]
        out[par] = {"mix": top, "share": cnt / n, "n": n}
        if verbose:
            cur = {70: (4, 12, 2), 71: (4, 11, 3), 72: (4, 10, 4), 73: (4, 9, 5)}.get(par)
            flag = "" if cur == top else "  <-- RULE SAYS %s" % (cur,)
            print("     par %d: %s in %d/%d events (%.0f%%)%s"
                  % (par, top, cnt, n, 100 * cnt / n, flag))
    return out


def main():
    print("=" * 72)
    print("PGA CONSTANT CALIBRATION — measuring what was assumed")
    print("=" * 72)
    print()
    r = fit_rho()
    print()
    ks = fit_k_shrink()
    print()
    ss = fit_sig_shrink()
    print()
    kf = fit_k_fit()
    print()
    kc = fit_k_course()
    print()
    kh = fit_k_h()
    print()
    pm = validate_par_mix()
    print()
    hl = tune_half_life()
    print()
    print("=" * 72)
    print("SUMMARY  (assumed -> measured)")
    print("=" * 72)
    def fmt(v):
        return "OFF (inf)" if v == float("inf") else "%.1f" % v
    print("  RHO         0.25  ->  %.3f" % (r["rho"] if r else float("nan")))
    print("  K_SHRINK    12.0  ->  %s" % (fmt(ks["k"]) if ks else "n/a"))
    print("  SIG_SHRINK  20.0  ->  %s" % (fmt(ss["k"]) if ss else "n/a"))
    print("  K_FIT        8.0  ->  %s" % (fmt(kf["k"]) if kf else "n/a"))
    print("  K_COURSE     2.0  ->  %s" % (fmt(kc["k"]) if kc else "n/a"))
    for par in sorted(kh or {}):
        print("  K_H par %d   60.0  ->  %s" % (par, fmt(kh[par])))
    print("  HALF_LIFE  120.0  ->  %s" % ("no decay" if hl["best"] > 9999 else hl["best"]))
    return {"rho": r, "k_shrink": ks, "sig_shrink": ss, "k_fit": kf, "k_course": kc,
            "k_h": kh, "par_mix": pm, "half_life": hl}


if __name__ == "__main__":
    main()
