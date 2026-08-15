#!/usr/bin/env python3
"""GM-001 — does DISTANCE pay more on courses with more PAR 5s? The cheapest course x skill test.

AUDIT CONTEXT. The frozen pga_ruler fits on ROUND SCORES ONLY (event_id, date, player, rnd,
score). Strokes-gained as a MAIN effect is already tested and rejected (pga_sg.py: partials ~0
once SG_TOT is known, every blend hurt, because the rating already correlates +0.876 with SG_TOT
and is built from finer round-level data). Personal course history is already rejected (true
variance 0.0715 against 7.49 of round noise). What has NOT been resolved is the INTERACTION:
does a course's architecture change WHICH skill pays?

WHY THIS INTERACTION FIRST. Par mix is the one course characteristic that is
  (a) genuinely variable  -- par-5 counts run 2,3,4,5 across 130 course-editions
                             (27 editions have 2 par-5s, 54 have 4), total par 70-73;
  (b) ARCHITECTURAL, so it is on the scorecard weeks ahead and carries NO look-ahead. Contrast
      score_diff / birdies / bogeys in the same table, which are that tournament's own OUTCOME
      and may only be used from PRIOR editions;
  (c) mechanistically tied to a skill we hold: par 5s are the primary birdie-and-eagle
      opportunity, and reaching them in two is a function of driving distance.

If distance does not pay more where there are more par 5s, the whole "course archetype x skill"
programme is much less likely to pay elsewhere, and that is worth knowing for one query.

DESIGN
  target      resid = (round score - field mean) - as-of rating   [what the model MISSES]
  skill       DRIVE_DIST, prior-SEASON only (leak control already enforced when ix was built)
  course      n_par5 for the course actually played
  model       resid ~ a + b*z(skill) + c*z(n_par5) + d*z(skill)*z(n_par5)
              d is the test. Main effects are IN so the interaction cannot absorb them.

  SINGLE-COURSE EVENTS ONLY. 13 of 114 tournaments run multiple courses (American Express uses
  3), and `rounds` does not record which course a player played on a given day, so a round there
  cannot be attributed to a par mix. Including them would assign the wrong architecture to most
  of those rounds.

  DEV 2024 -> VALIDATE 2025. 2026 IS THE PROTECTED HOLDOUT AND IS NOT READ AT ALL.

  Clustered by EVENT-ROUND: everyone in a round shares weather, setup and pin positions, so
  treating 150 players in one round as 150 independent observations would shrink every SE by
  roughly sqrt(150).

  PLACEBO: re-run with par mixes SHUFFLED ACROSS COURSES. The real coefficient must beat the
  placebo distribution, not merely differ from zero -- with ~75 courses, some interaction will
  look significant by chance.
"""
import math
import re
import sqlite3
from collections import Counter, defaultdict

import numpy as np

IX = "/home/ubuntu/pga_interactions.sqlite"
PM = "pga_model.sqlite"

# ── bridge: ix.event_id (ESPN) -> course_holes.tid (PGA), via event name + year ────────────────
pm = sqlite3.connect("file:%s?mode=ro" % PM, uri=True, timeout=60)
ix = sqlite3.connect("file:%s?mode=ro" % IX, uri=True, timeout=60)

STOP = {"the", "at", "of", "in", "presented", "by", "an", "a", "and", "tournament",
        "championship", "classic", "invitational", "open", "pro-am", "proam"}


def toks(s):
    t = re.sub(r"[^a-z0-9 ]", " ", str(s or "").lower()).split()
    return set(t) - STOP


ev_rows = pm.execute("SELECT DISTINCT event_id, event, substr(date,1,4) FROM rounds").fetchall()
th_rows = pm.execute("SELECT DISTINCT tid, tname FROM course_holes").fetchall()
tid_year = {t: int(re.match(r"R(\d{4})", t).group(1)) for t, _n in th_rows
            if re.match(r"R(\d{4})", t)}

bridge, ambig = {}, 0
for eid, evn, yr in ev_rows:
    a = toks(evn)
    cand = []
    for tid, tn in th_rows:
        if tid_year.get(tid) != int(yr):
            continue
        b = toks(tn)
        if not a or not b:
            continue
        j = len(a & b) / len(a | b)
        if j > 0:
            cand.append((j, tid))
    if not cand:
        continue
    cand.sort(reverse=True)
    if len(cand) > 1 and abs(cand[0][0] - cand[1][0]) < 1e-9 and cand[0][1] != cand[1][1]:
        ambig += 1
        continue
    if cand[0][0] >= 0.5:
        bridge[eid] = cand[0][1]
print("bridge: %d event_ids -> tid (%d ambiguous dropped)" % (len(bridge), ambig))

# VERIFY the bridge by PLAYER OVERLAP, not by name similarity that built it.
bird = defaultdict(set)
for tid, pl in pm.execute("SELECT tid, player FROM birdie_rounds"):
    bird[tid].add(str(pl).lower())
rnd_pl = defaultdict(set)
for eid, pl in pm.execute("SELECT event_id, player FROM rounds"):
    rnd_pl[eid].add(str(pl).lower())
ok = bad = 0
for eid, tid in bridge.items():
    a, b = rnd_pl.get(eid, set()), bird.get(tid, set())
    if not b:
        continue
    j = len(a & b) / max(len(b), 1)
    if j >= 0.6:
        ok += 1
    else:
        bad += 1
print("   verified by player overlap: %d good, %d suspicious (dropped below)" % (ok, bad))
good = set()
for eid, tid in bridge.items():
    a, b = rnd_pl.get(eid, set()), bird.get(tid, set())
    if b and len(a & b) / max(len(b), 1) >= 0.6:
        good.add(eid)

# ── course architecture: par mix, SINGLE-course tids only ──────────────────────────────────────
holes = defaultdict(lambda: Counter())
tid_courses = defaultdict(set)
for tid, cid, par in pm.execute("SELECT tid, course_id, par FROM course_holes"):
    holes[(tid, cid)][int(par)] += 1
    tid_courses[tid].add(cid)
single = {t for t, c in tid_courses.items() if len(c) == 1}
par5, par3, totpar = {}, {}, {}
for (tid, cid), c in holes.items():
    if tid in single:
        par5[tid] = c[5]
        par3[tid] = c[3]
        totpar[tid] = sum(p * n for p, n in c.items())
print("single-course tids with par mix: %d" % len(par5))
pm.close()

# ── assemble ───────────────────────────────────────────────────────────────────────────────────
rows = ix.execute("SELECT event_id, date, year, rnd, player, resid, DRIVE_DIST, DRIVE_ACC, "
                  "SG_OTT, SG_APP, SG_PUTT, SG_ARG, SCRAMBLE, GIR FROM ix").fetchall()
ix.close()
SKILLS = ["DRIVE_DIST", "DRIVE_ACC", "SG_OTT", "SG_APP", "SG_PUTT", "SG_ARG", "SCRAMBLE", "GIR"]
D = []
drop = Counter()
for r in rows:
    eid, date, yr, rnd, pl, res = r[0], r[1], int(r[2]), int(r[3]), r[4], r[5]
    if yr >= 2026:
        drop["2026 PROTECTED HOLDOUT"] += 1
        continue
    tid = bridge.get(eid)
    if tid is None or eid not in good:
        drop["no verified tid"] += 1
        continue
    if tid not in par5:
        drop["multi-course or no par mix"] += 1
        continue
    if res is None:
        drop["null resid"] += 1
        continue
    D.append(dict(eid=eid, tid=tid, yr=yr, rnd=rnd, pl=pl, res=float(res),
                  p5=float(par5[tid]), p3=float(par3[tid]), tp=float(totpar[tid]),
                  sk={k: float(v) for k, v in zip(SKILLS, r[6:]) if v is not None}))
print("\nusable rows %d | dropped: %s" % (len(D), dict(drop)))
if len(D) < 2000:
    raise SystemExit("insufficient rows")
print("dev 2024 %d | validate 2025 %d | courses %d"
      % (sum(1 for d in D if d["yr"] == 2024), sum(1 for d in D if d["yr"] == 2025),
         len({d["tid"] for d in D})))
print("par-5 counts in play: %s" % dict(Counter(d["p5"] for d in D)))


def z(v):
    v = np.asarray(v, float)
    s = v.std()
    return (v - v.mean()) / (s if s > 1e-12 else 1.0)


def fit_ols(X, y):
    return np.linalg.lstsq(X, y, rcond=None)[0]


def run(rows_, skill, cfeat, label, verbose=True):
    tr = [d for d in rows_ if d["yr"] == 2024 and skill in d["sk"]]
    te = [d for d in rows_ if d["yr"] == 2025 and skill in d["sk"]]
    if len(tr) < 500 or len(te) < 500:
        return None
    sk_tr = z([d["sk"][skill] for d in tr])
    cf_tr = z([d[cfeat] for d in tr])
    y_tr = np.array([d["res"] for d in tr])
    X_tr = np.column_stack([np.ones(len(tr)), sk_tr, cf_tr, sk_tr * cf_tr])
    b = fit_ols(X_tr, y_tr)
    # clustered SE by event-round on the DEV fit
    cl = defaultdict(list)
    resid_tr = y_tr - X_tr @ b
    for d, e in zip(tr, resid_tr):
        cl[(d["eid"], d["rnd"])].append(e)
    XtXi = np.linalg.pinv(X_tr.T @ X_tr)
    meat = np.zeros((4, 4))
    idx = defaultdict(list)
    for i, d in enumerate(tr):
        idx[(d["eid"], d["rnd"])].append(i)
    for g in idx.values():
        Xg = X_tr[g]
        ug = resid_tr[g]
        s = Xg.T @ ug
        meat += np.outer(s, s)
    V = XtXi @ meat @ XtXi
    se = math.sqrt(max(V[3, 3], 0))
    # OOS on 2025, standardised with the DEV moments (no peeking at test scale)
    m_s = np.mean([d["sk"][skill] for d in tr]); s_s = np.std([d["sk"][skill] for d in tr]) or 1
    m_c = np.mean([d[cfeat] for d in tr]); s_c = np.std([d[cfeat] for d in tr]) or 1
    sk_te = (np.array([d["sk"][skill] for d in te]) - m_s) / s_s
    cf_te = (np.array([d[cfeat] for d in te]) - m_c) / s_c
    y_te = np.array([d["res"] for d in te])
    X_te = np.column_stack([np.ones(len(te)), sk_te, cf_te, sk_te * cf_te])
    b_no = b.copy(); b_no[3] = 0.0
    mse_i = float(np.mean((y_te - X_te @ b) ** 2))
    mse_0 = float(np.mean((y_te - X_te @ b_no) ** 2))
    if verbose:
        print("   %-28s d=%+.4f (clustered SE %.4f, t=%+.2f)  OOS MSE %.4f -> %.4f  %s"
              % (label, b[3], se, b[3] / se if se > 0 else 0, mse_0, mse_i,
                 "BETTER" if mse_i < mse_0 else "worse"))
    return dict(d=b[3], se=se, t=b[3] / se if se > 0 else 0.0,
                gain=mse_0 - mse_i, n_tr=len(tr), n_te=len(te))


print("\n" + "=" * 96)
print("GM-001 — resid ~ skill + course + skill x course   (dev 2024, OOS 2025, 2026 UNTOUCHED)")
print("=" * 96)
print("   target sd = %.3f strokes; any real effect will be small against that" %
      np.std([d["res"] for d in D]))
print()
main = run(D, "DRIVE_DIST", "p5", "DRIVE_DIST x n_par5")

print("\n   other skill x par-5 pairings (same design):")
res_all = {}
for s in SKILLS:
    if s == "DRIVE_DIST":
        continue
    r = run(D, s, "p5", "%s x n_par5" % s)
    if r:
        res_all[s] = r

print("\n   distance against other architecture features:")
for cf, lab in (("p3", "n_par3"), ("tp", "total par")):
    run(D, "DRIVE_DIST", cf, "DRIVE_DIST x %s" % lab)

# ── PLACEBO: shuffle the par mix across courses ────────────────────────────────────────────────
print("\n" + "=" * 96)
print("PLACEBO — par mixes SHUFFLED ACROSS COURSES (the architecture is now a lie)")
print("=" * 96)
rng = np.random.default_rng(7)
tids = sorted({d["tid"] for d in D})
real_t = main["t"] if main else 0.0
null_t = []
for it in range(200):
    perm = list(tids)
    rng.shuffle(perm)
    mp = {a: par5[b] for a, b in zip(tids, perm)}
    Dp = [dict(d, p5=float(mp[d["tid"]])) for d in D]
    r = run(Dp, "DRIVE_DIST", "p5", "", verbose=False)
    if r:
        null_t.append(r["t"])
null_t = np.array(null_t)
print("   real t = %+.2f" % real_t)
print("   placebo t: mean %+.2f  sd %.2f  |t| >= real in %d/%d permutations (p = %.3f)"
      % (null_t.mean(), null_t.std(), int((np.abs(null_t) >= abs(real_t)).sum()), len(null_t),
         (np.abs(null_t) >= abs(real_t)).sum() / max(len(null_t), 1)))

print("\n" + "=" * 96)
print("VERDICT")
print("=" * 96)
p = (np.abs(null_t) >= abs(real_t)).sum() / max(len(null_t), 1)
if main and main["gain"] > 0 and p < 0.05:
    print("   SURVIVES: interaction is signed, beats its placebo, and improves OOS MSE.")
else:
    print("   REJECTED: %s%s%s"
          % ("no OOS gain. " if main and main["gain"] <= 0 else "",
             "placebo not beaten (p=%.3f). " % p if p >= 0.05 else "",
             "Distance does not pay differentially by par-5 count."))
