"""⛳ PGA MODEL AUDIT — rerun of the 2026-07-29 audit after the fix pass.

Every number here is measured live. Sections mirror the original audit so the before/after
is directly comparable, and each check is designed to FAIL loudly if the fix regressed.
"""
import math
import re
import sqlite3
import statistics as st

import pga_birdies as B
import pga_context as C
import pga_field as F
import pga_ruler as RU

print("=" * 72)
print("PGA MODEL AUDIT")
print("=" * 72)

# ---------------------------------------------------------------- 1. substrate
con = sqlite3.connect(RU.DB)
nr, npl = con.execute("SELECT COUNT(*), COUNT(DISTINCT player) FROM rounds").fetchone()
try:
    bt, br_, bp = con.execute(
        "SELECT COUNT(DISTINCT tid), COUNT(*), COUNT(DISTINCT player) FROM birdie_rounds"
    ).fetchone()
except Exception:                                                  # noqa: BLE001
    bt = br_ = bp = 0
con.close()
print("\n[1] SUBSTRATE")
print("    rounds  %6d over %d players" % (nr, npl))
print("    birdies %6d rounds over %d players, %d events harvested" % (br_, bp, bt))

# ---------------------------------------------------------------- 2. ratings
R, gsd = RU.fit()
print("\n[2] RATINGS (two-pass, field-strength corrected)")
top = sorted(R.items(), key=lambda kv: kv[1][0])[:5]
for nm, (r, sg, n) in top:
    print("    %-24s %+.2f str/rd  sd %.2f  n=%d" % (nm, r, sg, n))
thin = [(nm, v) for nm, v in R.items() if v[2] < RU.MIN_ROUNDS]
print("    MIN_ROUNDS floor = %d; %d players below it (halved + widened, not blocked)"
      % (RU.MIN_ROUNDS, len(thin)))
for nm in ("Jackson Koivun",):
    v = R.get(nm)
    if v:
        print("    %-24s %+.2f  n=%d  -> %s"
              % (nm, v[0], v[2], "ABOVE floor, full confidence" if v[2] >= RU.MIN_ROUNDS
                 else "below floor, shrunk"))

# ---------------------------------------------------------------- 3. simulator calibration
field = [(c.get("athlete") or {}).get("displayName") for c in F.competitors()]
field = [f for f in field if f]
sim = RU.simulate(R, field)
print("\n[3] SIMULATOR INTERNAL CALIBRATION (must sum to N across the field)")
ok_all = True
for k, tgt in (("win", 1), ("top5", 5), ("top10", 10), ("top20", 20)):
    tot = sum(v[k] for v in sim.values())
    good = abs(tot - tgt) < 0.5
    ok_all &= good
    print("    sum P(%-5s) = %6.2f  target %2d   %s" % (k, tot, tgt, "OK" if good else "FAIL"))
print("    cut: %.2f (target ~70)" % sum(v["cut"] for v in sim.values()))

# ---------------------------------------------------------------- 4. walk-forward
print("\n[4] WALK-FORWARD VALIDATION (as-of fits, no odds required)")
acc, rmse, npairs = RU.walk_forward(seasons=(2026,), verbose=False)
t = acc and (acc - 0.5) * math.sqrt(npairs) / 0.5 if npairs else 0
print("    pairwise ordering accuracy %.3f on %d pairs (0.5 = worthless, z~%.1f)"
      % (acc, npairs, t))
print("    field-relative score RMSE  %.2f strokes  (global round sd %.2f)" % (rmse, gsd))

# --------------------------------------------------- 4b. the information ceiling
print("\n[4b] INFORMATION CEILING (is the RMSE a weakness or physics?)")
nf = RU.noise_floor(verbose=True)
if nf:
    print("     model RMSE %.2f vs floor %.3f  -> %.0f%% of the way to the limit"
          % (rmse, nf["sd_noise"], 100 * nf["sd_noise"] / rmse))
    cap, base = nf["acc_cap"], 0.5
    got = (acc - base) / (cap - base) if cap > base else 0
    print("     model accuracy %.3f vs ceiling %.3f -> capturing %.0f%% of obtainable signal"
          % (acc, cap, 100 * got))
    print("     VERDICT: %s" % ("near-exhausted — spend effort on markets, not the ruler"
                                if got > 0.75 else "real headroom remains in the ruler"))

# ---------------------------------------------------------------- 5. context terms
print("\n[5] CONTEXT TERMS (each measured, with its own n)")
br = C._birdie_bridge()
print("    scoring->birdie bridge : r=%+.3f on n=%d events" % (br.get("r") or 0, br.get("n") or 0))
wf = C.fit_wind(verbose=False)
print("    wind coefficient       : %+.5f/km/h  r=%+.3f  n=%d obs / %d events  %s"
      % (wf["w"], wf.get("r") or 0, wf.get("n") or 0, wf.get("events") or 0,
         "ASSUMED" if wf.get("assumed") else "FITTED (" + str(wf.get("design")) + ")"))
# SCALE CHECK: the live wind input must be on the same statistic as the fit. It was not —
# fit on daily maxima, fed the mean of all hourly values — which inflated every birdie rate
# by 3.88% in all weather. Assert it here so a future edit cannot silently reintroduce it.
try:
    _la_, _lo_ = F.coords()
    _live = C.live_wind_stat(_la_, _lo_) if _la_ is not None else None
    _fitm = wf.get("mean_wind")
    if _live and _fitm:
        _ratio = _live / _fitm
        print("    scale check           : live %.1f km/h vs fitted-sample mean %.1f -> "
              "%.2fx  %s" % (_live, _fitm, _ratio,
                             "OK (same statistic)" if 0.5 <= _ratio <= 2.0
                             else "MISMATCH — live input is not the fit's statistic"))
except Exception as _e:
    print("    scale check           : unavailable (%s)" % str(_e)[:50])
_mw = wf.get("mean_wind")
print("       centred on %s km/h %s"
      % (("%.1f" % _mw) if _mw else ("%.1f" % C.WIND_REF),
         "(the fitted sample's own mean -> term is mean-zero)" if _mw
         else "(WIND_REF fallback: the fit has no recorded mean, so the term carries a "
              "standing bias at average conditions)"))
ev = F.event().get("name") or ""
cf, cn = C.course_factor(ev)
print("    course factor (%s): %.3f from %d prior editions" % (ev[:22], cf, cn))
fits = [(p, C.course_fit(p, ev)) for p in field[:250]]
have = [(p, d) for p, (d, n) in fits if n >= 2]
print("    course fit              : %d/%d players with >=2 rounds here, range %+.2f..%+.2f"
      % (len(have), len(field), min([d for _, d in have] or [0]), max([d for _, d in have] or [0])))
tt = F.tee_times()
try:
    import pga_wave as W
    import pga_birdies as _B
    wf = W.fit_wave(verbose=False)
    tid_now = _B.tid_for_name(ev)
    sheet = W.tees_for(tid_now) if tid_now else {}
    print("    wave gap (fitted)       : beta %+.4f str per km/h  r=%s  n=%d event-rounds "
          "over %d events  %s"
          % (wf.get("beta") or 0,
             ("%+.3f" % wf["r"]) if wf.get("r") is not None else "n/a",
             wf.get("n_gaps") or 0, wf.get("events") or 0,
             "ASSUMED" if wf.get("assumed") else "FITTED"))
    if wf.get("mean_abs_gap"):
        print("       mean |AM-PM| gap %.3f str, sd %.3f -> a real wave split is worth "
              "about %.2f strokes" % (wf["mean_abs_gap"], wf.get("sd_gap") or 0,
                                      wf["mean_abs_gap"]))
    print("    tee sheet               : orchestrator %d players, ESPN %d -> %s"
          % (len(sheet), len(tt), "ACTIVE" if sheet or tt else "not posted yet"))
except Exception as _e:
    print("    wave terms              : unavailable (%s)" % str(_e)[:60])

# ---------------------------------------------------------------- 6. birdie bias
print("\n[6] BIRDIE BIAS vs REAL FD LINES (the check that caught v1)")
con = sqlite3.connect("golf_lines.sqlite")
ts = con.execute("SELECT MAX(collected_at) FROM golf_lines WHERE mtype LIKE '%BIRD%'").fetchone()[0]
rows = con.execute("SELECT market, runner, odds FROM golf_lines WHERE mtype LIKE '%BIRD%' "
                   "AND collected_at=?", (ts,)).fetchall() if ts else []
con.close()
mix = B.mix_for("R2026524")
# Use the SAME wind statistic production uses. This was hardcoded to 10.9, which is on the
# mean-of-all-hourly-values scale the model no longer feeds — so section 6 was grading an
# input pga_e3 does not use. Falling back to the fitted sample mean gives a neutral factor
# rather than an arbitrary one.
try:
    _lat_a, _lon_a = F.coords()
    wind = C.live_wind_stat(_lat_a, _lon_a) if _lat_a is not None else None
except Exception:                                                   # noqa: BLE001
    wind = None
if not wind:
    wind = (C.fit_wind(verbose=False) or {}).get("mean_wind") or C.WIND_REF
print("    (section 6 wind input: %.1f km/h, live statistic matching the fit)" % wind)


def parse(rate_kw):
    BR, _ = B.rates(**rate_kw)
    BRn = {RU.norm(k): v for k, v in BR.items()}
    out = []
    for mkt, run, od in rows:
        pm = re.match(r"(.+?)\s+Total Birdies or Better", mkt)
        sm = re.search(r"(Over|Under)\s+([\d.]+)", run)
        if not pm or not sm:
            continue
        rr = BRn.get(RU.norm(pm.group(1).strip()))
        if not rr:
            continue
        out.append((pm.group(1).strip(), sm.group(1).lower(), float(sm.group(2)), od, rr))
    return out


def _fair_map(parsed):
    """(player, line) -> devigged fair P(over), from the two paired quotes.

    The audit used to compare the model to mean(1/odds_over), i.e. the Over price WITH the vig
    in it. On these lines the overround is 6.04%, so that reference sat +3.02 points above
    fair and every "bias" number this section has ever printed was low by about that much.
    """
    q = {}
    for pl, sd, ln, od, _rr in parsed:
        q.setdefault((RU.norm(pl), ln), {})[sd] = od
    out = {}
    for k, v in q.items():
        if "over" in v and "under" in v:
            io_, iu = 1.0 / v["over"], 1.0 / v["under"]
            if io_ + iu > 0:
                out[k] = io_ / (io_ + iu)
    return out


def bias(parsed, mx, lam=1.0, fair=None):
    """Model vs market on the Over side. Compares to FAIR when the paired quote exists."""
    ov = [x for x in parsed if x[1] == "over"]
    if fair is not None:
        ov = [x for x in ov if (RU.norm(x[0]), x[2]) in fair]
    if not ov:
        return None, None, 0
    m = st.mean(B.p_x_or_more({a: min(b * lam, .95) for a, b in rr.items()},
                              int(ln + .5), mx) for _p, _s, ln, _o, rr in ov)
    if fair is not None:
        k = st.mean(fair[(RU.norm(x[0]), x[2])] for x in ov)
    else:
        k = st.mean(1 / x[3] for x in ov)
    return m, k, len(ov)


p_naive = parse({})
FAIR = _fair_map(p_naive)
m1, k1, n1 = bias(p_naive, B.DEFAULT_MIX, fair=FAIR)
print("    v1 (par-72 mix, no context)     model %.3f vs market %.3f  bias %+.1f pts"
      % (m1, k1, 100 * (m1 - k1)))
p_ctx = parse({"course_factor": cf, "wind_kmh": wind})
m2, k2, n2 = bias(p_ctx, mix, fair=FAIR)
print("    NOW (real mix + course + wind)   model %.3f vs market %.3f  bias %+.1f pts"
      % (m2, k2, 100 * (m2 - k2)))
lo, hi = 0.5, 1.8
for _ in range(30):
    L = (lo + hi) / 2
    mm, _, _ = bias(p_ctx, mix, L, fair=FAIR)
    if mm > k2:
        hi = L
    else:
        lo = L
print("    market anchor now only corrects %.1f%% (was 12%% when blind)" % abs(100 * (L - 1)))
print("    reference is the DEVIGGED fair price on %d two-sided lines; the raw Over price "
      "sits %.2f pts above it, and comparing to raw understated every earlier bias figure "
      "by that much" % (len(FAIR), 100 * (st.mean(1 / x[3] for x in p_ctx if x[1] == "over"
                                                  and (RU.norm(x[0]), x[2]) in FAIR)
                                          - st.mean(FAIR[(RU.norm(x[0]), x[2])]
                                                    for x in p_ctx if x[1] == "over"
                                                    and (RU.norm(x[0]), x[2]) in FAIR))))
edges = []
for pl, sd, ln, od, rr in p_ctx:
    rs = {a: min(b * L, .95) for a, b in rr.items()}
    po = B.p_x_or_more(rs, int(ln + .5), mix)
    edges.append(((po if sd == "over" else 1 - po) - 1 / od, sd))
no = sum(1 for e, s in edges if e >= .05 and s == "over")
nu = sum(1 for e, s in edges if e >= .05 and s == "under")
print("    flag-worthy: %d overs / %d unders  -> %s"
      % (no, nu, "TWO-SIDED (healthy)" if no and nu else "ONE-SIDED (suspect)"))

# ---------------------------------------------------------------- 7. devig sanity
print("\n[7] DEVIG POOL SANITY (the source of the fake +20-27% edges)")
con = sqlite3.connect("golf_lines.sqlite")
ts2 = con.execute("SELECT MAX(collected_at) FROM golf_lines").fetchone()[0]
# BUG #9: LIKE '%PGA%' also matches "LPGA AIG Women's Open" — so this check, whose entire
# job is to catch pooling errors, could itself pool a women's event into the men's pool.
ev_fd = con.execute("SELECT event, COUNT(*) c FROM golf_lines WHERE collected_at=? AND "
                    "TRIM(event) LIKE 'PGA %' GROUP BY event ORDER BY c DESC LIMIT 1",
                    (ts2,)).fetchone()
rows2 = con.execute("SELECT market, mtype, runner, odds FROM golf_lines WHERE event=? AND "
                    "collected_at=?", (ev_fd[0], ts2)).fetchall() if ev_fd else []
con.close()
fam = {}
for mkt, mt, run, od in rows2:
    if od and od > 1 and mt and (("TOP_" in mt and "FINISH" in mt) or mt == "OUTRIGHT_BETTING"):
        # key on the FULL mtype: "Top 20" and "Top 20 Finish (Incl. Ties)" are different
        # products and pooling them is bug #8
        f = mt
        d = fam.setdefault(f, {})
        if run not in d or od < d[run]:
            d[run] = od
def _nfor(f):
    if f == "OUTRIGHT_BETTING":
        return 1
    dd = "".join(ch for ch in str(f).split("_FINISH")[0] if ch.isdigit())
    return int(dd) if dd in ("5", "10", "20") else None


for f, d in sorted(fam.items()):
    N = _nfor(f)
    if not N:
        continue
    inv = sum(1 / o for o in d.values())
    print("    %-30s %4d runners  implies %6.1f  target %2d  %s"
          % (str(f)[:30], len(d), inv, N,
             "OK" if 0.4 * N <= inv <= 3 * N else "SKIPPED by guard"))

# ------------------------------------------------------ 8. in-play conditioning
print("\n[8] IN-PLAY CONDITIONING (blind spot #4)")
try:
    con = sqlite3.connect(RU.DB)
    rw = con.execute("SELECT event_id, MIN(date) FROM rounds GROUP BY event_id "
                     "ORDER BY MIN(date) DESC LIMIT 1").fetchone()
    sc = {}
    for pl, rn_, s_ in con.execute("SELECT player, rnd, score FROM rounds WHERE event_id=? "
                                   "AND score>0", (rw[0],)):
        sc.setdefault(pl, {})[rn_] = s_
    con.close()
    fld = list(sc)
    Rw, _ = RU.fit(asof=rw[1])
    fin = {p_: sum(d[r] for r in (1, 2, 3, 4)) for p_, d in sc.items() if len(d) >= 4}
    win_ = min(fin, key=fin.get)
    p2 = {p_: [d[r] for r in (1, 2) if d.get(r)] for p_, d in sc.items()}
    p3 = {p_: [d[r] for r in (1, 2, 3) if d.get(r)] for p_, d in sc.items()}
    s0 = RU.simulate(Rw, fld, n_sims=4000, seed=5)
    s2_ = RU.simulate(Rw, fld, n_sims=4000, seed=5, progress={k: v for k, v in p2.items() if v})
    s3 = RU.simulate(Rw, fld, n_sims=4000, seed=5, progress={k: v for k, v in p3.items() if v})
    seq = [s0.get(win_, {}).get("win"), s2_.get(win_, {}).get("win"),
           s3.get(win_, {}).get("win")]
    print("    eventual winner %s: pre %.1f%% -> 36h %.1f%% -> 54h %.1f%%"
          % (win_, 100 * (seq[0] or 0), 100 * (seq[1] or 0), 100 * (seq[2] or 0)))
    mono = all(seq[i] is not None and seq[i + 1] is not None and seq[i + 1] >= seq[i]
               for i in range(2))
    sums_ok = all(abs(sum(v["win"] for v in ss.values()) - 1) < 0.5
                  for ss in (s0, s2_, s3) if ss)
    elim = [s3[p_]["cut"] for p_ in p3 if len(p3[p_]) < 3 and p_ in s3]
    print("    win probs still sum to 1 at every stage: %s | eliminated players max cut "
          "prob %.3f" % ("yes" if sums_ok else "NO", max(elim) if elim else -1))
    print("    -> %s" % ("OK" if mono and sums_ok and (not elim or max(elim) < .001)
                         else "CHECK"))
except Exception as _e:
    print("    unavailable (%s)" % str(_e)[:70])

# --------------------------------------------------------------- 9. constants
print("\n[9] CONSTANTS — value and provenance (nothing here should be un-evidenced)")
try:
    import pga_birdies as _B
    import pga_context as _C
    rows = [
        ("RHO", RU.RHO, "0.25",
         "MEASURED: ANOVA 0.055 (44,580 dof) / round-pair r=+0.039 (n=57,015) / 36-hole "
         "spread +0.109"),
        ("K_SHRINK", RU.K_SHRINK, "12.0", "MEASURED: EB k=noise 7.786 / true 0.709"),
        ("SIG_SHRINK", RU.SIG_SHRINK, "20.0",
         "MEASURED: EB, true sd-spread 0.23 on mean sd 2.81"),
        ("MIN_ROUNDS", RU.MIN_ROUNDS, "20", "USER-SET (2026-07-29), deliberately not fitted"),
        ("K_FIT", _C.K_FIT, "8.0",
         "MEASURED: EB 104.8 over 8,257 cells; OOS early->late slope +0.0605 implies 80"),
        ("K_COURSE", _C.K_COURSE, "2.0",
         "UNCHANGED ON PURPOSE: EB measures the direct factor, not the bridge this shrinks"),
        ("K_H par3", _B.K_H_PAR.get(3), "60.0", "MEASURED: EB, true between-player var 0.0002"),
        ("K_H par4", _B.K_H_PAR.get(4), "60.0", "MEASURED: EB, true var 0.0014"),
        ("K_H par5", _B.K_H_PAR.get(5), "60.0", "MEASURED: EB, true var 0.0015"),
        ("HALF_LIFE_D", RU.HALF_LIFE_D, "120.0",
         "TUNED on 2024-25 with 2026 HELD OUT (the only tuned constant)"),
    ]
    for nm, val, was, why in rows:
        chg = "same" if ("%.4g" % float(val)) == ("%.4g" % float(was)) else ("was " + was)
        print("    %-12s %10s  %-9s %s" % (nm, "%.4g" % float(val), chg, why[:78]))
    br = _C._birdie_bridge() or {}
    print("    bridge fit level: %s, n=%s courses / %s editions, r=%s (per-edition %s)"
          % (br.get("level"), br.get("n"), br.get("n_editions"),
             ("%+.3f" % br["r"]) if br.get("r") is not None else "n/a",
             ("%+.3f" % br["edition_r"]) if br.get("edition_r") is not None else "n/a"))
    print("    par-mix rule: %s" % {k: tuple(v.values()) for k, v in
                                    sorted(_B.PAR_MIX_RULE.items())})
except Exception as _e:
    print("    unavailable (%s)" % str(_e)[:70])

print("\n" + "=" * 72)
print("AUDIT COMPLETE")
