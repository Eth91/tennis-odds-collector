"""Close the five blind spots the 2026-07-29 audit named. Idempotent + AST-validated.

  #1 wave dormant/assumed  -> pga_wave.py (new) reads the orchestrator tee sheet, which is
                              posted days before ESPN's stamp, and FITS the AM/PM gap.
  #2 birdies 2026-only     -> completed_tournaments(year=) + harvest(years=) unlock 2024-25,
                              and course birdie factors get measured DIRECTLY instead of
                              being inferred through the scoring bridge.
  #3 RMSE ~= field sd      -> noise_floor() decomposes round variance into skill vs
                              irreducible noise, so we learn whether 2.82 is a weakness or
                              the information ceiling. This one gets ANSWERED, not patched:
                              if the floor is 2.80 there is nothing left to win, and knowing
                              that stops us burning weeks on the round model.
  #4 no in-play            -> simulate(progress=, partial=) conditions on rounds already
                              posted and on a partially played round.
  #5 G2 stuck at n=3       -> g2_gate also grades 18-hole (round) matchbets. Cannot invent
                              settled closes, but 72-hole-only threw away the round markets,
                              which settle daily and are the softest book on the sheet.

MEMORY NOTE: simulate() runs every loop tick on a VM whose cgroup we deliberately squeezed,
so the pre-tournament path is left byte-for-byte as it was and never materialises a full
(n_sims, k, 4) round array. Only the in-play path, which a human triggers, pays that cost.
"""
import ast
import io

APPLIED = []


def patch(path, old, new, tag, probe=None):
    s = io.open(path, encoding="utf-8").read()
    if (probe or new.strip()[:60]) in s:
        print("  = %-18s %s (already applied)" % (path, tag))
        return
    assert old in s, "ANCHOR MISSING in %s for %s" % (path, tag)
    s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8").write(s)
    APPLIED.append((path, tag))
    print("  + %-18s %s" % (path, tag))


# ===================================================================== #2 seasons
patch("pga_birdies.py", '''def completed_tournaments():
    d = gql('{schedule(tourCode: "R") {completed {tournaments {id tournamentName}}}}')
    out = []
    for grp in (d.get("data", {}).get("schedule", {}) or {}).get("completed") or []:
        for t in grp.get("tournaments") or []:
            if str(t.get("id", "")).startswith("R2026"):
                out.append((t["id"], t["tournamentName"]))
    return out
''', '''def completed_tournaments(year=None):
    """Completed events for a season. `schedule` takes a year argument, which is what makes
    the 2024-25 backfill possible — v1 hard-coded the R2026 prefix and could only ever see
    the current season, so every course birdie factor had to come through the bridge."""
    q = ('{schedule(tourCode: "R"%s) {completed {tournaments {id tournamentName}}}}'
         % ((', year: "%d"' % int(year)) if year else ""))
    d = gql(q)
    pref = "R%d" % int(year) if year else "R2026"
    out = []
    for grp in (d.get("data", {}).get("schedule", {}) or {}).get("completed") or []:
        for t in grp.get("tournaments") or []:
            if str(t.get("id", "")).startswith(pref):
                out.append((t["id"], t["tournamentName"]))
    return out


def upcoming_tournaments(year=None):
    """Upcoming events — the bettable ones, and the tee sheets worth polling."""
    q = ('{schedule(tourCode: "R"%s) {upcoming {tournaments {id tournamentName}}}}'
         % ((', year: "%d"' % int(year)) if year else ""))
    d = gql(q)
    out = []
    for grp in (d.get("data", {}).get("schedule", {}) or {}).get("upcoming") or []:
        for t in grp.get("tournaments") or []:
            if t.get("id"):
                out.append((t["id"], t.get("tournamentName") or ""))
    return out
''', "multi-season schedule")

patch("pga_birdies.py", '''def harvest(max_events=None):
    con = sqlite3.connect(DB)
    con.execute(DDL)
    done = {r[0] for r in con.execute("SELECT DISTINCT tid FROM birdie_rounds")}
    evs = [e for e in completed_tournaments() if e[0] not in done]
    if max_events:
        evs = evs[:max_events]
    print(f"harvest: {len(evs)} new events (of {len(completed_tournaments())} completed 2026)")
''', '''def harvest(max_events=None, years=(2026,)):
    """Default stays 2026 so the loop's behaviour is unchanged; pass years=(2024, 2025) for
    the backfill. Idempotent by tid, so re-running only fetches what is missing."""
    con = sqlite3.connect(DB)
    con.execute(DDL)
    done = {r[0] for r in con.execute("SELECT DISTINCT tid FROM birdie_rounds")}
    allev = []
    for yr in years:
        allev += completed_tournaments(year=yr)
    evs = [e for e in allev if e[0] not in done]
    if max_events:
        evs = evs[:max_events]
    print(f"harvest: {len(evs)} new events (of {len(allev)} completed in {list(years)})")
''', "harvest(years=)")

# ============================================== #2b direct course birdie factor
patch("pga_context.py", '''def course_factor(event_name, verbose=False):''',
      '''def direct_course_birdie_factor(event_name):
    """Observed/expected BIRDIE rate at this course from prior editions we hold hole-level
    data for. This is the measurement the bridge was standing in for: the bridge infers
    birdies from scoring (r=-0.68 — good, but lossy), while this counts the actual holes.
    Returns (factor, n_editions, n_rounds); factor is None with no direct history."""
    key = (event_name or "").strip().lower()
    toks = [w for w in key.replace("pga", "").split() if len(w) > 3 and not w.isdigit()]
    if not toks:
        return None, 0, 0
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT tid, tname, COUNT(*), SUM(p3h), SUM(p3b), SUM(p4h), SUM(p4b), "
        "SUM(p5h), SUM(p5b) FROM birdie_rounds GROUP BY tid").fetchall()
    tot = con.execute("SELECT SUM(p3h), SUM(p3b), SUM(p4h), SUM(p4b), SUM(p5h), SUM(p5b) "
                      "FROM birdie_rounds").fetchone()
    con.close()
    if not tot or not tot[0]:
        return None, 0, 0
    g = {3: tot[1] / tot[0] if tot[0] else .15, 4: tot[3] / tot[2] if tot[2] else .15,
         5: tot[5] / tot[4] if tot[4] else .15}
    obs_h = obs_b = exp_b = 0.0
    eds = nrd = 0
    for _tid, tname, nr, a3, b3, a4, b4, a5, b5 in rows:
        el = str(tname or "").lower()
        if sum(1 for w in toks if w in el) < max(1, len(toks) // 2):
            continue
        h = (a3 or 0) + (a4 or 0) + (a5 or 0)
        if not h:
            continue
        eds += 1
        nrd += nr or 0
        obs_h += h
        obs_b += (b3 or 0) + (b4 or 0) + (b5 or 0)
        exp_b += (a3 or 0) * g[3] + (a4 or 0) * g[4] + (a5 or 0) * g[5]
    if not obs_h or exp_b <= 0:
        return None, 0, 0
    raw = obs_b / exp_b
    # shrink on ROUNDS, not editions: four rounds of one edition is not a course read
    w = nrd / (nrd + 300.0)
    return max(0.75, min(1.30, 1.0 + (raw - 1.0) * w)), eds, nrd


def course_factor(event_name, verbose=False):''', "direct birdie factor")

patch("pga_context.py", '''    d = st.mean(diffs)
    raw = br["a"] + br["b"] * d
    n = len(diffs)
    fac = 1.0 + (raw - 1.0) * n / (n + K_COURSE)
    fac = max(0.75, min(1.30, fac))''', '''    d = st.mean(diffs)
    raw = br["a"] + br["b"] * d
    n = len(diffs)
    fac = 1.0 + (raw - 1.0) * n / (n + K_COURSE)
    fac = max(0.75, min(1.30, fac))
    # PREFER DIRECT HOLE HISTORY where we hold it (blind spot #2). The bridge is an
    # inference from scoring; counted birdies are the thing itself. Blend on rounds so one
    # thin edition cannot outvote a well-fit bridge.
    dfac, deds, dnrd = direct_course_birdie_factor(event_name)
    if dfac is not None and dnrd >= 200:
        wd = dnrd / (dnrd + 400.0)
        fac = fac * (1 - wd) + dfac * wd
        if verbose:
            print(f"  direct birdie history: {deds} edition(s), {dnrd} rounds -> "
                  f"{dfac:.3f}, blended weight {wd:.2f} -> {fac:.3f}")''',
      "blend direct into course_factor", probe="PREFER DIRECT HOLE HISTORY")

# ======================================================= #5 needs re in the ruler
patch("pga_ruler.py", '''import math
import sqlite3
import statistics as st''', '''import math
import re
import sqlite3
import statistics as st''', "import re", probe="import re\nimport sqlite3")

# =============================================================== #3 noise floor
patch("pga_ruler.py", '''def g2_gate(verbose=True):''', '''def noise_floor(verbose=True):
    """How much of round-to-round scoring is knowable AT ALL.

    The audit flagged RMSE 2.82 against a global round sd of 2.92 as a weakness. That
    framing assumes the whole gap is model error. Decompose it instead: the variance of
    field-relative scores splits into BETWEEN-player (skill, learnable) and WITHIN-player
    (day-to-day noise, learnable by nothing). sqrt(within) is the RMSE floor for ANY
    predictor, and it also caps pairwise ordering, because two players whose true skills
    differ by d only order correctly with probability Phi(d / (sd_noise * sqrt(2))).

    If our RMSE sits at that floor and our accuracy sits at that ceiling, the weakness is
    golf rather than the ruler — and more work on the round model is wasted motion.
    """
    con = sqlite3.connect(DB)
    raw = {}
    for eid, rnd, pl, sc in con.execute(
            "SELECT event_id, rnd, player, score FROM rounds WHERE score > 0"):
        raw.setdefault((eid, rnd), {})[norm(pl)] = sc
    con.close()
    per = defaultdict(list)
    allrel = []
    for _k, d in raw.items():
        if len(d) < 40:
            continue
        m = st.mean(d.values())
        for p, s in d.items():
            per[p].append(s - m)
            allrel.append(s - m)
    if len(allrel) < 500:
        if verbose:
            print("  noise_floor: not enough rounds")
        return None
    var_tot = st.pvariance(allrel)
    # pooled UNBIASED within-player variance over players with enough rounds to estimate it
    num = den = 0.0
    skill = []
    for p, v in per.items():
        if len(v) >= 8:
            num += st.variance(v) * (len(v) - 1)
            den += len(v) - 1
            skill.append(st.mean(v))
    var_within = num / den if den else var_tot
    # the observed spread of player means overstates skill by var_within/n_rounds per player
    ns = [len(per[p]) for p in per if len(per[p]) >= 8]
    nbar = st.mean(ns) if ns else 1
    var_between = max(st.pvariance(skill) - var_within / nbar, 0.0) if len(skill) > 2 else 0.0
    sd_noise = math.sqrt(var_within)
    sd_skill = math.sqrt(var_between)
    # ceiling on pairwise ordering accuracy, averaged over the REAL distribution of skill
    # gaps rather than an assumed one
    import random as _rnd
    rr = _rnd.Random(11)
    acc_cap, N = 0.0, 20000
    for _ in range(N):
        a, b = rr.choice(skill), rr.choice(skill)
        acc_cap += _phi(abs(a - b) / (sd_noise * math.sqrt(2)))
    acc_cap /= N
    out = {"sd_total": math.sqrt(var_tot), "sd_noise": sd_noise, "sd_skill": sd_skill,
           "acc_cap": acc_cap, "n_rounds": len(allrel), "n_players": len(skill),
           "skill_share": var_between / max(var_tot, 1e-9)}
    if verbose:
        print("  VARIANCE DECOMPOSITION (%d rounds, %d players with >=8 rounds)"
              % (len(allrel), len(skill)))
        print("     total sd             %.3f strokes" % out["sd_total"])
        print("     within-player noise  %.3f  <- IRREDUCIBLE RMSE floor" % sd_noise)
        print("     between-player skill %.3f  <- the only learnable part" % sd_skill)
        print("     skill share of variance %.1f%%" % (100 * out["skill_share"]))
        print("     => pairwise accuracy CEILING %.3f  (0.5 = coin flip)" % acc_cap)
    return out


def g2_gate(verbose=True):''', "noise_floor")

# ==================================================================== #4 in-play
patch("pga_ruler.py", '''def simulate(R, field, n_sims=8000, seed=7, course_fit=None, wave=None,
             wave_shift=0.0):''', '''def simulate(R, field, n_sims=8000, seed=7, course_fit=None, wave=None,
             wave_shift=0.0, progress=None, partial=None):''', "simulate signature",
      probe="wave_shift=0.0, progress=None, partial=None")

patch("pga_ruler.py", '''    eps = rng.normal(0, 1, (n_sims, k, 4)) * (sig * math.sqrt(1 - RHO))[None, :, None]
    tot2 = 2 * (mus + wk) + eps[:, :, :2].sum(2)          # 36-hole totals
    cutline = np.sort(tot2, axis=1)[:, min(69, k - 1)][:, None]
    made = tot2 <= cutline
    tot4 = tot2 + np.where(made, 2 * (mus + wk) + eps[:, :, 2:].sum(2), 1e6)''',
      '''    eps = rng.normal(0, 1, (n_sims, k, 4)) * (sig * math.sqrt(1 - RHO))[None, :, None]
    forced = None
    if not progress:
        # PRE-TOURNAMENT PATH — unchanged. This runs every loop tick on a memory-capped
        # cgroup, so it deliberately never materialises a full (n_sims, k, 4) round array.
        tot2 = 2 * (mus + wk) + eps[:, :, :2].sum(2)      # 36-hole totals
        rest = 2 * (mus + wk) + eps[:, :, 2:].sum(2)
    else:
        # IN-PLAY CONDITIONING (blind spot #4). A posted round is a FACT, so it replaces its
        # simulated draw instead of being re-rolled. Scores arrive as raw strokes while the
        # ruler lives in field-relative space, so each round is demeaned by that round's own
        # field mean — computed from the posted scores themselves, the same baseline fit()
        # uses. A partially played round carries its strokes-so-far plus a variance-scaled
        # draw for the holes that remain (mu*f, sd*sqrt(f)).
        prog = {norm(p): list(v or []) for p, v in progress.items()}
        means = {}
        for j in range(4):
            vals = [v[j] for v in prog.values() if len(v) > j and v[j]]
            if len(vals) >= 20:
                means[j] = float(np.mean(vals))
        known = np.zeros((k, 4))
        kmask = np.zeros((k, 4))
        frac = np.ones((k, 4))
        for i, p in enumerate(names):
            v = prog.get(norm(p)) or []
            for j in range(4):
                if len(v) > j and v[j] and j in means:
                    known[i, j] = v[j] - means[j]
                    kmask[i, j] = 1.0
        if partial:
            part = {norm(p): v for p, v in partial.items()}
            for i, p in enumerate(names):
                pv = part.get(norm(p))
                if not pv:
                    continue
                thru, rel_thru = pv
                j = int(kmask[i].sum())
                if not (0 < thru < 18) or j > 3:
                    continue
                frac[i, j] = (18.0 - thru) / 18.0
                known[i, j] = rel_thru
                kmask[i, j] = 0.5                         # half-known: keep a scaled draw
        full = (kmask == 1.0)[None, :, :]
        half = (kmask == 0.5)[None, :, :]
        r_all = (mus + wk)[:, :, None] + eps
        if half.any():
            sc = np.sqrt(frac)[None, :, :]
            r_all = np.where(half, known[None, :, :] + (mus[None, :, None] * frac[None, :, :]
                                                        + wk[:, :, None] * frac[None, :, :]
                                                        + eps * sc), r_all)
        r_all = np.where(full, known[None, :, :], r_all)
        tot2 = r_all[:, :, :2].sum(2)
        rest = r_all[:, :, 2:].sum(2)
        # a third round on the board is proof the cut was made
        forced = np.array([kmask[i, 2] > 0 for i in range(k)])
    cutline = np.sort(tot2, axis=1)[:, min(69, k - 1)][:, None]
    made = tot2 <= cutline
    if forced is not None and forced.any():
        made = made | forced[None, :]
    tot4 = tot2 + np.where(made, rest, 1e6)''', "in-play conditioning",
      probe="IN-PLAY CONDITIONING")

# ============================================================= #5 evidence rate
patch("pga_ruler.py", '''    for (evn, mkt), rr in by_m.items():
        if len(rr) != 2 or "Round" in mkt:
            continue
        (a, oa, _), (b, ob, _) = rr
        # results: both players' 72-hole totals at an event matching by fuzzy name + recency
        toks = [t for t in evn.replace("PGA", "").split() if len(t) > 3 and not t.isdigit()]
        if not toks:
            continue
        row = conr.execute(
            "SELECT event_id, date FROM rounds WHERE event LIKE ? GROUP BY event_id "
            "ORDER BY date DESC LIMIT 1", ("%" + toks[0] + "%",)).fetchone()
        if not row:
            continue
        eid, edate = row
        sa = conr.execute("SELECT SUM(score), COUNT(*) FROM rounds WHERE event_id=? AND "
                          "player=?", (eid, a)).fetchone()
        sb = conr.execute("SELECT SUM(score), COUNT(*) FROM rounds WHERE event_id=? AND "
                          "player=?", (eid, b)).fetchone()
        if not sa[0] or not sb[0] or sa[1] != 4 or sb[1] != 4 or sa[0] == sb[0]:
            continue
        y = 1.0 if sa[0] < sb[0] else 0.0
        p_book = (1 / oa) / (1 / oa + 1 / ob)             # devig close
        if edate not in fits:
            R, _ = fit(asof=edate)
            fits[edate] = {norm(k): v for k, v in R.items()}
        p_rul = matchup_prob(fits[edate], a, b, rounds=4)
        if p_rul is None:
            continue''', '''    n_fam = defaultdict(int)
    for (evn, mkt), rr in by_m.items():
        if len(rr) != 2:
            continue
        # ROUND matchbets count too (blind spot #5). v1 graded 72-hole markets only, which
        # settle once a week and left G2 at n=3 for weeks — while '18 Hole Matchbet (Round
        # N)', the softest book on the sheet, settled daily and was thrown away. Same
        # rigour either way: real collected closes, as-of ratings, actual scores.
        rm = re.search(r"\\(Round (\\d)\\)", mkt)
        rn = int(rm.group(1)) if rm else None
        (a, oa, _), (b, ob, _) = rr
        # results at an event matched by fuzzy name + recency
        toks = [t for t in evn.replace("PGA", "").split() if len(t) > 3 and not t.isdigit()]
        if not toks:
            continue
        row = conr.execute(
            "SELECT event_id, date FROM rounds WHERE event LIKE ? GROUP BY event_id "
            "ORDER BY date DESC LIMIT 1", ("%" + toks[0] + "%",)).fetchone()
        if not row:
            continue
        eid, edate = row
        if rn:
            sa = conr.execute("SELECT score, 1 FROM rounds WHERE event_id=? AND player=? "
                              "AND rnd=?", (eid, a, rn)).fetchone()
            sb = conr.execute("SELECT score, 1 FROM rounds WHERE event_id=? AND player=? "
                              "AND rnd=?", (eid, b, rn)).fetchone()
            if not sa or not sb or not sa[0] or not sb[0] or sa[0] == sb[0]:
                continue
        else:
            sa = conr.execute("SELECT SUM(score), COUNT(*) FROM rounds WHERE event_id=? AND "
                              "player=?", (eid, a)).fetchone()
            sb = conr.execute("SELECT SUM(score), COUNT(*) FROM rounds WHERE event_id=? AND "
                              "player=?", (eid, b)).fetchone()
            if not sa[0] or not sb[0] or sa[1] != 4 or sb[1] != 4 or sa[0] == sb[0]:
                continue
        y = 1.0 if sa[0] < sb[0] else 0.0
        p_book = (1 / oa) / (1 / oa + 1 / ob)             # devig close
        if edate not in fits:
            R, _ = fit(asof=edate)
            fits[edate] = {norm(k): v for k, v in R.items()}
        p_rul = matchup_prob(fits[edate], a, b, rounds=(1 if rn else 4))
        if p_rul is None:
            continue
        n_fam["R%d" % rn if rn else "72H"] += 1''', "g2 accepts round matchbets")

patch("pga_ruler.py", '''        if n_used < 15:
            print(f"G2: only {n_used} gradeable closed matchups so far — gate INCONCLUSIVE, "
                  f"keep collecting (it self-answers as tournaments settle)")''',
      '''        fam = " ".join("%s=%d" % kv for kv in sorted(n_fam.items()))
        if n_used < 15:
            print(f"G2: only {n_used} gradeable closed matchups so far [{fam}] — gate "
                  f"INCONCLUSIVE, keep collecting (it self-answers as events settle)")''',
      "g2 reports families")

print("\nverifying every touched module parses")
for f in ("pga_birdies.py", "pga_context.py", "pga_ruler.py"):
    ast.parse(io.open(f, encoding="utf-8").read())
    print("  ok %s" % f)
print("applied %d patch(es)" % len(APPLIED))
