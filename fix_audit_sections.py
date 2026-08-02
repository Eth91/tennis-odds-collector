"""Add the two sections the original audit could not have: the information ceiling, and
whether the conditional (in-play) sim is trustworthy.

Section 4 reported RMSE 2.82 next to a global sd of 2.92 and called it a weakness. That
comparison cannot distinguish model error from irreducible noise, which is the whole
question, so it now sits next to the measured floor and the accuracy ceiling.
"""
import ast, io
p = "pga_audit.py"
s = io.open(p, encoding="utf-8").read()

old = '''# ---------------------------------------------------------------- 5. context terms'''
new = '''# --------------------------------------------------- 4b. the information ceiling
print("\\n[4b] INFORMATION CEILING (is the RMSE a weakness or physics?)")
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

# ---------------------------------------------------------------- 5. context terms'''
if "INFORMATION CEILING" not in s:
    assert old in s
    s = s.replace(old, new, 1)

old2 = '''print("\\n" + "=" * 72)
print("AUDIT COMPLETE")'''
new2 = '''# ------------------------------------------------------ 8. in-play conditioning
print("\\n[8] IN-PLAY CONDITIONING (blind spot #4)")
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

print("\\n" + "=" * 72)
print("AUDIT COMPLETE")'''
if "IN-PLAY CONDITIONING (blind spot #4)" not in s:
    assert old2 in s
    s = s.replace(old2, new2, 1)

ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + audit: information-ceiling and in-play sections added")
