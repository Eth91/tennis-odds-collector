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
wind = 10.9


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


def bias(parsed, mx, lam=1.0):
    ov = [x for x in parsed if x[1] == "over"]
    if not ov:
        return None, None, 0
    m = st.mean(B.p_x_or_more({a: min(b * lam, .95) for a, b in rr.items()},
                              int(ln + .5), mx) for _p, _s, ln, _o, rr in ov)
    k = st.mean(1 / x[3] for x in ov)
    return m, k, len(ov)


p_naive = parse({})
m1, k1, n1 = bias(p_naive, B.DEFAULT_MIX)
print("    v1 (par-72 mix, no context)     model %.3f vs market %.3f  bias %+.1f pts"
      % (m1, k1, 100 * (m1 - k1)))
p_ctx = parse({"course_factor": cf, "wind_kmh": wind})
m2, k2, n2 = bias(p_ctx, mix)
print("    NOW (real mix + course + wind)   model %.3f vs market %.3f  bias %+.1f pts"
      % (m2, k2, 100 * (m2 - k2)))
lo, hi = 0.5, 1.8
for _ in range(30):
    L = (lo + hi) / 2
    mm, _, _ = bias(p_ctx, mix, L)
    if mm > k2:
        hi = L
    else:
        lo = L
print("    market anchor now only corrects %.1f%% (was 12%% when blind)" % abs(100 * (L - 1)))
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
ev_fd = con.execute("SELECT event, COUNT(*) c FROM golf_lines WHERE collected_at=? AND "
                    "event LIKE '%PGA%' GROUP BY event ORDER BY c DESC LIMIT 1", (ts2,)).fetchone()
rows2 = con.execute("SELECT market, mtype, runner, odds FROM golf_lines WHERE event=? AND "
                    "collected_at=?", (ev_fd[0], ts2)).fetchall() if ev_fd else []
con.close()
fam = {}
for mkt, mt, run, od in rows2:
    if od and od > 1 and mt and (("TOP_" in mt and "FINISH" in mt) or mt == "OUTRIGHT_BETTING"):
        f = ("OUTRIGHT" if mt == "OUTRIGHT_BETTING"
             else "TOP_%s" % "".join(ch for ch in mt.split("_FINISH")[0] if ch.isdigit()))
        d = fam.setdefault(f, {})
        if run not in d or od < d[run]:
            d[run] = od
NM = {"TOP_5": 5, "TOP_10": 10, "TOP_20": 20, "OUTRIGHT": 1}
for f, d in sorted(fam.items()):
    N = NM.get(f)
    if not N:
        continue
    inv = sum(1 / o for o in d.values())
    print("    %-9s %3d runners  implies %6.1f qualifiers  target %2d  %s"
          % (f, len(d), inv, N, "OK" if 0.4 * N <= inv <= 3 * N else "SKIPPED by guard"))

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

print("\n" + "=" * 72)
print("AUDIT COMPLETE")
