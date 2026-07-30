"""⛳ PHASE-2 FAIR-PRICE RULER (PGA_PLAN.md) — one round-score engine, four market pricers.

WHAT THIS IS: a mispricing DETECTOR, not an oracle (the plan's words). It prices round/72-hole
matchups, outrights and top-N finishes from field-adjusted round-score distributions, and it
earns the right to flag anything ONLY by passing GATE G2: on real collected FanDuel closes,
its matchup log-loss must land within ~2pts of the devigged close. A ruler that can't get
close to the close cannot tell soft from sharp — the K-SIM lesson.

WHY THIS ARCHITECTURE AND NOT THE TRANSFORMER WISH LIST: the rating substrate is (player,
round, score-vs-field) — ESPN publishes every round score for every season in ONE call per
year. On ~40k rounds/season, a recency-weighted shrunk mean + per-player variance is within
noise of anything fancier, fits in milliseconds, can't silently overfit, and every number in
it can be printed and argued with. State-of-the-art here means the VALIDATION is rigorous,
not that the estimator is exotic (constitution laws 3, 4, 6).

MODEL. r_i = recency-weighted mean of (score_i - field_mean_event_round), shrunk toward 0
(field average) by K_SHRINK pseudo-rounds; sigma_i = player round-score sd shrunk to the
global sd. A round is simulated as r_i + week_i + eps, where week_i ~ N(0, RHO*sig^2) is a
player-week form effect shared across the event's rounds (the plan's round-to-round
dependence) and eps ~ N(0, (1-RHO)*sig^2). Tournament outcomes come from Monte Carlo with a
top-65-and-ties-proxy cut after R2.
"""
import datetime as dt
import json
import math
import re
import sqlite3
import statistics as st
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "pga_model.sqlite"
LINES = HERE / "golf_lines.sqlite"
UA = {"User-Agent": "Mozilla/5.0"}

HALF_LIFE_D = 270.0     # TUNED 2026-07-29 on 2024-25 with 2026 HELD OUT — the only tuned
                        # constant here. Tune-set curve is a clean interior peak:
                        #   45d .5721  60d .5779  90d .5809  120d .5833  180d .5847
                        #   270d .5862 <-best  365d .5849  no-decay .5811
                        # 'No decay' scoring worse than 120 shows recency IS real; it just
                        # acts over ~9 months, and 120 sat on the wrong side of the peak.
                        # HELD-OUT 2026: .5885 -> .5967 (+.0082), i.e. 85% -> 93% of the
                        # measured 0.604 ordering ceiling. RMSE prefers ~90-120 and gives up
                        # 0.0003 here; taken deliberately, since matchups and top-N are
                        # priced off ordering and the ordering gain is ~15x the RMSE cost.
K_SHRINK = 11.0         # MEASURED 2026-07-29 (was 12.0, a guess that turned out close).
                        # Empirical-Bayes optimum k = noise var / true between-player var =
                        # 7.786 / 0.709 over 659 players with >=8 rounds.
RHO = 0.05              # MEASURED 2026-07-29, was 0.25 — FIVE TIMES too high. Three
                        # independent estimates: nested ANOVA on rounds within vs across
                        # events = 0.055 (44,580 dof, and the only one that needs no
                        # ratings); raw round-pair correlation r=+0.039 on 57,015 pairs;
                        # selection-free 36-hole total spread implies +0.109. All in
                        # [0.034, 0.109]. A player's four rounds are very nearly
                        # independent. At 0.25 the model inflated 72-hole variance ~14%,
                        # which pushed matchup prices toward 50/50 and fattened the top-N
                        # tails. (The first attempt at this used 72-hole totals and implied
                        # a NEGATIVE rho — an artefact of cut selection, since only
                        # cut-makers have four rounds.)
SIG_SHRINK = 78.0       # MEASURED 2026-07-29 (was 20.0). The TRUE spread of player
                        # volatility is tiny: between-player variance of sd is 0.052
                        # (sd 0.23) around a mean sd of 2.81 — an 8% spread — against
                        # sampling noise of 4.02 per observation. So 'some players are
                        # streakier' is mostly an illusion and own-sd deserves far less
                        # weight. k = 4.020 / 0.052.
SPREAD = 1.30           # TUNED 2026-07-30 on 2025, HELD-OUT confirmed on 2026 (mean
                        # |slope-1| .4464 -> .1602, a 64% cut). Widens rating DEVIATIONS from the
                        # field before any rank/matchup calc. K_SHRINK is right for a point
                        # estimate but a rank sim is non-linear, so shrunk inputs made the field
                        # look homogeneous and compressed every tournament probability toward its
                        # base rate. Sigma was ruled out first: it tests clean in every rating bin.
MIN_ROUNDS = 20         # user 2026-07-29: '20 rounds or less is a good rule'. Below
                        # this a rating is HALVED toward field-average and sigma widens
                        # — it still prices (Koivun at 46 rounds is genuinely good and
                        # unaffected), it just stops speaking with unearned confidence.


def _get(url):
    return json.load(urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=40))


def crawl(seasons=(2023, 2024, 2025, 2026)):
    """Season scoreboards -> rounds(player, event, date, round, score). Idempotent."""
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS rounds(
        event_id TEXT, event TEXT, date TEXT, player TEXT, rnd INTEGER, score REAL,
        PRIMARY KEY(event_id, player, rnd))""")
    for yr in seasons:
        d = _get("https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=%d" % yr)
        n = 0
        for ev in d.get("events") or []:
            eid, enm = str(ev.get("id")), ev.get("name") or ""
            edate = (ev.get("date") or "")[:10]
            for comp in ev.get("competitions") or []:
                for c in comp.get("competitors") or []:
                    nm = ((c.get("athlete") or {}).get("displayName") or "").strip()
                    if not nm:
                        continue
                    for i, ls in enumerate(c.get("linescores") or []):
                        v = ls.get("value")
                        if isinstance(v, (int, float)) and 55 <= v <= 100:
                            con.execute("INSERT OR REPLACE INTO rounds VALUES (?,?,?,?,?,?)",
                                        (eid, enm, edate, nm, i + 1, float(v)))
                            n += 1
        con.commit()
        print(f"  crawl {yr}: +{n} round rows")
    total = con.execute("SELECT COUNT(*), COUNT(DISTINCT player) FROM rounds").fetchone()
    print(f"  rounds table: {total[0]} rows, {total[1]} players")
    con.close()


def all_rows():
    """Every round, sorted by date — pass to fit(rows=...) to avoid re-querying per as-of
    fit. A half-life grid search is ~350 fits and the query dominates otherwise."""
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT event_id, date, player, rnd, score FROM rounds "
                       "ORDER BY date").fetchall()
    con.close()
    return rows


def fit(asof=None, rows=None, half_life=None, k_shrink=None, sig_shrink=None,
        min_rounds=None):
    """{player: (rating, sigma, n_rounds)} using ONLY rounds strictly before `asof`.

    The four constants are overridable so pga_calib can measure them; passing None keeps the
    module default, so every existing caller is unaffected.
    """
    asof = asof or "9999"
    HL = float(half_life if half_life is not None else HALF_LIFE_D)
    KS = float(k_shrink if k_shrink is not None else K_SHRINK)
    SS = float(sig_shrink if sig_shrink is not None else SIG_SHRINK)
    MR = int(min_rounds if min_rounds is not None else MIN_ROUNDS)
    if rows is None:
        con = sqlite3.connect(DB)
        rows = con.execute("SELECT event_id, date, player, rnd, score FROM rounds "
                           "WHERE date < ? ORDER BY date", (asof,)).fetchall()
        con.close()
    else:
        rows = [r for r in rows if r[1] < asof]
    by_er = defaultdict(list)
    for eid, date, nm, rnd, sc in rows:
        by_er[(eid, rnd)].append(sc)
    fmean = {k: st.mean(v) for k, v in by_er.items() if len(v) >= 20}
    ref = dt.date.fromisoformat(asof[:10]) if asof != "9999" else dt.date.today()

    # TWO-PASS FIELD-STRENGTH CORRECTION (2026-07-29 audit, blindness #4). Ratings are
    # strokes-vs-field-mean, so beating a Korn-Ferry-grade field by 2 counted the same as
    # beating a signature field by 2 — opposite-field regulars were systematically
    # flattered. Pass 1 = the naive fit; pass 2 subtracts each event-round's OWN field
    # quality (the mean pass-1 rating of everyone who teed off in it), so the baseline a
    # player is measured against reflects who he actually played.
    prov = {}
    tmp = defaultdict(list)
    for eid, date, nm, rnd, sc in rows:
        fm = fmean.get((eid, rnd))
        if fm is not None:
            tmp[nm].append(sc - fm)
    for nm, v in tmp.items():
        prov[nm] = st.mean(v) * len(v) / (len(v) + KS)
    fq = defaultdict(list)
    for eid, date, nm, rnd, sc in rows:
        if nm in prov:
            fq[(eid, rnd)].append(prov[nm])
    fieldq = {k: st.mean(v) for k, v in fq.items() if len(v) >= 20}

    per = defaultdict(list)
    for eid, date, nm, rnd, sc in rows:
        fm = fmean.get((eid, rnd))
        if fm is None:
            continue
        # a round's baseline is its field mean OFFSET by that field's quality: a strong
        # field's mean score is low because the field is strong, not because it was easy.
        fm = fm - fieldq.get((eid, rnd), 0.0)
        try:
            age = (ref - dt.date.fromisoformat(date)).days
        except ValueError:
            continue
        w = 0.5 ** (max(age, 0) / HL)
        per[nm].append((sc - fm, w))
    g_sd = st.pstdev([d for v in per.values() for d, _ in v]) or 2.8
    out = {}
    for nm, v in per.items():
        sw = sum(w for _, w in v)
        mu = sum(d * w for d, w in v) / sw if sw else 0.0
        rating = mu * sw / (sw + KS)                     # shrink to field average
        n = len(v)
        sd = st.pstdev([d for d, _ in v]) if n >= 5 else g_sd
        sigma = (sd * n + g_sd * SS) / (n + SS)
        if n < MR:
            rating, sigma = rating * 0.5, max(sigma, g_sd * 1.15)
        out[nm] = (rating, sigma, n)
    return out, g_sd


def norm(n):
    return " ".join(str(n or "").lower().replace(".", "").split())


def _phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2)))


def matchup_prob(R, a, b, rounds=1, course_fit=None):
    """P(A beats B) over `rounds` rounds, ties excluded (two-way no-push price).
    The player-week effect is fresh each event, so it adds variance but cancels nothing."""
    ra = R.get(norm(a)) or R.get(a)
    rb = R.get(norm(b)) or R.get(b)
    if not ra or not rb:
        return None
    (ma, sa, _), (mb, sb, _) = ra, rb
    cf = course_fit or {}
    # SPREAD must be applied here too, or matchup prices and the tournament sim would disagree
    # about the same two players. The field mean of a shrunk rating set is ~0 by construction.
    _all = [v[0] for v in R.values()]
    _rm = (sum(_all) / len(_all)) if _all else 0.0
    ma = _rm + SPREAD * (ma - _rm) + cf.get(a, cf.get(norm(a), 0.0))
    mb = _rm + SPREAD * (mb - _rm) + cf.get(b, cf.get(norm(b), 0.0))
    mu = (mb - ma) * rounds
    var = rounds * (sa * sa + sb * sb) + RHO * (sa * sa + sb * sb) * (rounds - 1)
    return _phi(mu / math.sqrt(max(var, 1e-6)))


def simulate(R, field, n_sims=8000, seed=7, course_fit=None, wave=None,
             wave_shift=0.0, progress=None, partial=None, reps=1):
    """reps>1 averages independent runs to cut Monte Carlo noise at CONSTANT peak memory.
    Measured across five seeds at 8000 sims, worst-case seed-to-seed sd was 0.70 points on
    top-20 and 1.00 on make-cut — 14-20% of the 5-point edge threshold, so a flagged 5.0%
    edge could be 4.3% or 5.7% from sampling alone. Four reps halve that; raising n_sims
    instead would quadruple a (n_sims, k, 4) array, which this 956MB box cannot afford."""
    if reps and reps > 1:
        acc = {}
        for i in range(int(reps)):
            one = simulate(R, field, n_sims=n_sims, seed=seed + 1000 * i,
                           course_fit=course_fit, wave=wave, wave_shift=wave_shift,
                           progress=progress, partial=partial, reps=1)
            if not one:
                return {}
            for pl, v in one.items():
                a = acc.setdefault(pl, {})
                for k_, val in v.items():
                    a[k_] = a.get(k_, 0.0) + val / float(reps)
        return acc
    """Win/top5/10/20/make-cut probs via MC: 4 rounds, player-week effect, top-70 cut."""
    import numpy as np
    rng = np.random.default_rng(seed)
    names = [p for p in field if (norm(p) in R or p in R)]
    # COURSE FIT (blindness #3): per-player strokes/round adjustment at THIS venue,
    # already shrunk by pga_context (course history is the most over-claimed golf edge).
    cf = course_fit or {}
    _r = [(R.get(norm(p)) or R[p])[0] for p in names]
    _rm = float(np.mean(_r)) if _r else 0.0
    # SPREAD: widen deviations from the field mean (see the constant's note above)
    mus = np.array([_rm + SPREAD * (v - _rm) + cf.get(p, cf.get(norm(p), 0.0))
                    for p, v in zip(names, _r)])
    sig = np.array([(R.get(norm(p)) or R[p])[1] for p in names])
    k = len(names)
    if k < 30:
        return {}
    wk = rng.normal(0, sig * math.sqrt(RHO), (n_sims, k))
    # WAVE-CORRELATED CUT (blindness #5): a windy wave misses the cut TOGETHER. Adding a
    # shared per-wave shift makes the cut line correlate within wave instead of treating
    # 143 players as independent draws — which is what made make-cut and top-N prices
    # over-confident in the tails.
    if wave and wave_shift:
        wv = np.array([1.0 if wave.get(p, wave.get(norm(p), "am")) == "pm" else -1.0
                       for p in names])
        wk = wk + (wave_shift / 2.0) * wv[None, :]
    # per-player sigma must broadcast across the ROUND axis; numpy cannot align a
    # (k,) scale against (n_sims, k, 4), so draw unit normals and scale explicitly.
    eps = rng.normal(0, 1, (n_sims, k, 4)) * (sig * math.sqrt(1 - RHO))[None, :, None]
    forced = gone = None
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
        # ELIMINATED PLAYERS CANNOT WIN. If the field has completed round j and a player has
        # no score for it, they missed the cut or withdrew. Without this they keep every
        # unplayed round as a simulated draw and free-roll a whole tournament: on the 2025
        # Rocket Classic that handed 70 eliminated players a 4-round run and pushed the
        # actual 54-hole leader down to a 1.5% win probability.
        maxj = max(means) if means else -1
        gone = np.array([any(kmask[i, j] <= 0 for j in range(maxj + 1)) for i in range(k)])
    # INTEGER SCORES (2026-07-30). Golf is scored in whole strokes; continuous draws make exact
    # ties impossible, which left top-N-INCL-TIES unpriceable and 3-balls wrong (a two-way tie for
    # low is a dead heat, not a win). Rounding here produces ties at their natural rate and yields
    # BOTH rank distributions from one pass.
    tot2 = np.rint(tot2)
    rest = np.rint(rest)
    cutline = np.sort(tot2, axis=1)[:, min(69, k - 1)][:, None]
    made = tot2 <= cutline
    if forced is not None and forced.any():
        made = made | forced[None, :]
    if gone is not None and gone.any():
        made = made & ~gone[None, :]
    tot4 = tot2 + np.where(made, rest, 1e6)
    order = tot4.argsort(1).argsort(1)                    # strict rank (ties broken arbitrarily)
    # TIE-AWARE POSITION: 1 + how many players are STRICTLY better. A tie shares the better rank,
    # which is how books settle "incl. ties".
    pos = (tot4[:, :, None] > tot4[:, None, :]).sum(2) + 1
    out = {}
    for i, p in enumerate(names):
        out[p] = {"win": float((order[:, i] == 0).mean()),
                  "top5": float((order[:, i] < 5).mean()),
                  "top10": float((order[:, i] < 10).mean()),
                  "top20": float((order[:, i] < 20).mean()),
                  # ties-inclusive: what the "(Incl. Ties)" products actually pay on
                  "win_ties": float((pos[:, i] == 1).mean()),
                  "top5_ties": float((pos[:, i] <= 5).mean()),
                  "top10_ties": float((pos[:, i] <= 10).mean()),
                  "top20_ties": float((pos[:, i] <= 20).mean()),
                  "cut": float(made[:, i].mean())}
    return out


def threeball(R, trio, rounds=1, n_sims=40000, seed=17, course_fit=None):
    """{player: {'win','tie','dead_heat_ev'}} for a 3-ball over `rounds` rounds.

    Integer scores matter here more than anywhere: at 18 holes a two-way tie for low is common,
    and FanDuel settles 3-balls as a dead heat (stake back proportionally) rather than a win. So
    'win' is the outright-low probability and 'dead_heat_ev' is what a unit actually returns —
    a full win plus a half share of two-way ties and a third of three-way ties.
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    trio = [p for p in (trio or []) if p]
    if len(trio) != 3:
        return {}                      # a 3-ball needs exactly three named players
    keys = []
    for p in trio:
        v = R.get(norm(p)) or R.get(p)
        if not v:
            return {}                  # unrated player: refuse rather than guess
        keys.append(v)
    cf = course_fit or {}
    mus = np.array([v[0] + cf.get(p, cf.get(norm(p), 0.0)) for p, v in zip(trio, keys)])
    sig = np.array([v[1] for v in keys])
    wk = rng.normal(0, sig * math.sqrt(RHO), (n_sims, 3))
    eps = rng.normal(0, 1, (n_sims, 3, rounds)) * (sig * math.sqrt(1 - RHO))[None, :, None]
    tot = np.rint((mus + wk)[:, :, None] + eps).sum(2)
    best = tot.min(1, keepdims=True)
    at_best = (tot == best)
    n_at = at_best.sum(1, keepdims=True)
    out = {}
    for i, p in enumerate(trio):
        sole = float(((n_at[:, 0] == 1) & at_best[:, i]).mean())
        tied = float(((n_at[:, 0] > 1) & at_best[:, i]).mean())
        # dead-heat return on a 1u stake: full on a sole win, 1/n of the stake back otherwise
        ev = float((at_best[:, i] / n_at[:, 0]).mean())
        out[p] = {"win": sole, "tie": tied, "dead_heat_ev": ev}
    return out


def walk_forward(seasons=(2025, 2026), verbose=True, season_max=None, rows=None,
                 **fitkw):
    """Validation that does NOT wait on odds. G2 needs settled matchup closes and sat at
    n=3 for weeks, which makes it unfalsifiable today. This scores the ruler against actual
    ROUND SCORES it never saw: for each event, fit strictly as-of its start date, then
    measure how well the predicted score ordering holds. Reported as pairwise accuracy
    (share of same-round player pairs where the better-rated player actually shot lower)
    plus RMSE against the field-relative score."""
    con = sqlite3.connect(DB)
    if season_max:
        evs = con.execute(
            "SELECT event_id, MIN(date) d, event FROM rounds GROUP BY event_id "
            "HAVING d >= ? AND d <= ? ORDER BY d",
            ("%d-01-01" % min(seasons), "%d-12-31" % int(season_max))).fetchall()
    else:
        evs = con.execute(
            "SELECT event_id, MIN(date) d, event FROM rounds GROUP BY event_id "
            "HAVING d >= ? ORDER BY d", ("%d-01-01" % min(seasons),)).fetchall()
    con.close()
    if rows is None and fitkw:
        rows = all_rows()          # only worth pre-loading when a grid is being searched
    import random
    random.seed(11)
    hits = tot = 0
    errs = []
    for eid, d0, ev in evs:
        R, _ = fit(asof=d0, rows=rows, **fitkw)
        Rn = {norm(k): v for k, v in R.items()}
        con = sqlite3.connect(DB)
        erows = con.execute("SELECT player, rnd, score FROM rounds WHERE event_id=?",
                            (eid,)).fetchall()
        con.close()
        by_r = defaultdict(list)
        for pl, rnd, sc in erows:
            r = Rn.get(norm(pl))
            if r:
                by_r[rnd].append((pl, r[0], sc))
        for rnd, lst in by_r.items():
            if len(lst) < 20:
                continue
            fm = st.mean(x[2] for x in lst)
            for pl, rt, sc in lst:
                errs.append((sc - fm) - rt)
            pairs = [(random.choice(lst), random.choice(lst)) for _ in range(60)]
            for (p1, r1, s1), (p2, r2, s2) in pairs:
                if p1 == p2 or s1 == s2 or abs(r1 - r2) < 0.15:
                    continue
                tot += 1
                if (r1 < r2) == (s1 < s2):
                    hits += 1
    acc = hits / tot if tot else 0.0
    rmse = (sum(e * e for e in errs) / len(errs)) ** 0.5 if errs else 0.0
    if verbose:
        print(f"  WALK-FORWARD (as-of fits, {len(evs)} events, no odds needed):")
        print(f"    pairwise ordering accuracy {acc:.3f} on {tot} pairs  (0.5 = worthless)")
        print(f"    field-relative score RMSE  {rmse:.2f} strokes over {len(errs)} rounds")
    return acc, rmse, tot


def noise_floor(verbose=True):
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


def _same_edition_event(conr, odds_event, any_ts):
    """Resolve an odds-book event name to the results event for the SAME EDITION.

    The old lookup took the most recent event matching the FIRST token, so "PGA Rocket Classic
    2026" resolved to the 2025 Rocket Classic and the gate scored 2026 prices against 2025
    results. Requires every distinctive token to match AND the year to agree; with no year in
    the name, falls back to the edition starting nearest after the price was collected.
    """
    toks = [t.lower() for t in str(odds_event or "").replace("PGA", "").split()
            if len(t) > 3 and not t.isdigit()]
    if not toks:
        return None, None
    yr = None
    m = re.search(r"\b(20\d\d)\b", str(odds_event or ""))
    if m:
        yr = m.group(1)
    cands = []
    for eid, d0, evn in conr.execute(
            "SELECT event_id, MIN(date), event FROM rounds GROUP BY event_id").fetchall():
        el = str(evn or "").lower()
        if not all(t in el for t in toks):
            continue
        if yr and not str(d0 or "").startswith(yr):
            continue
        if not yr and any_ts and str(d0 or "") < str(any_ts)[:10]:
            continue                      # an edition that finished before we saw the price
        cands.append((eid, d0))
    if not cands:
        return None, None
    cands.sort(key=lambda z: z[1])
    return cands[0]


def g2_gate(verbose=True):
    """GATE G2 on REAL collected FanDuel matchbet CLOSES: ruler log-loss vs the devigged
    close, on events whose results are in. Ratings are fit AS-OF each event's start date, so
    no result being judged is inside the training set.

    A "close" is the last price collected BEFORE the relevant round begins — the event start
    for a 72-hole matchup, start+(N-1) days for a round-N matchup. It used to be
    MAX(collected_at), which during a live event is an IN-PLAY price that already knows the
    result.
    """
    con = sqlite3.connect(LINES)
    raw = con.execute(
        "SELECT event, market, runner, odds, collected_at FROM golf_lines "
        "WHERE market LIKE '%Matchbet%' AND odds > 1.0").fetchall()
    con.close()
    by_m = defaultdict(list)
    for evn, mkt, run, od, ts in raw:
        by_m[(str(evn).strip(), mkt)].append((run, od, ts))
    conr = sqlite3.connect(DB)
    ll_book, ll_ruler, n_used = [], [], 0
    fits = {}
    n_fam = defaultdict(int)
    dropped = defaultdict(int)
    for (evn, mkt), quotes in by_m.items():
        rm = re.search(r"\(Round (\d)\)", mkt)
        rn = int(rm.group(1)) if rm else None
        eid, edate = _same_edition_event(conr, evn, min(q[2] for q in quotes))
        if not eid:
            dropped["no same-edition result yet"] += 1
            continue
        # the close: last price strictly before the relevant round tees off
        try:
            cutoff = dt.date.fromisoformat(str(edate)[:10])
            if rn:
                cutoff = cutoff + dt.timedelta(days=rn - 1)
        except ValueError:
            dropped["bad event date"] += 1
            continue
        best = {}
        for run, od, ts in quotes:
            if str(ts)[:10] > cutoff.isoformat():
                continue                 # in-play or post-round: not a close
            cur = best.get(run)
            if cur is None or str(ts) > str(cur[1]):
                best[run] = (od, ts)
        if len(best) != 2:
            dropped["no two-sided pre-round close"] += 1
            continue
        (a, (oa, _ta)), (b, (ob, _tb)) = list(best.items())
        if rn:
            sa = conr.execute("SELECT score FROM rounds WHERE event_id=? AND player=? AND "
                              "rnd=?", (eid, a, rn)).fetchone()
            sb = conr.execute("SELECT score FROM rounds WHERE event_id=? AND player=? AND "
                              "rnd=?", (eid, b, rn)).fetchone()
            if not sa or not sb or not sa[0] or not sb[0] or sa[0] == sb[0]:
                dropped["round not both posted / tie"] += 1
                continue
            ya, yb = sa[0], sb[0]
        else:
            sa = conr.execute("SELECT SUM(score), COUNT(*) FROM rounds WHERE event_id=? AND "
                              "player=?", (eid, a)).fetchone()
            sb = conr.execute("SELECT SUM(score), COUNT(*) FROM rounds WHERE event_id=? AND "
                              "player=?", (eid, b)).fetchone()
            if (not sa[0] or not sb[0] or sa[1] != 4 or sb[1] != 4 or sa[0] == sb[0]):
                dropped["72h not both complete / tie"] += 1
                continue
            ya, yb = sa[0], sb[0]
        y = 1.0 if ya < yb else 0.0
        p_book = (1 / oa) / (1 / oa + 1 / ob)             # devigged close
        if edate not in fits:
            R, _ = fit(asof=edate)
            fits[edate] = {norm(k): v for k, v in R.items()}
        p_rul = matchup_prob(fits[edate], a, b, rounds=(1 if rn else 4))
        if p_rul is None:
            dropped["player unrated as-of"] += 1
            continue
        p_rul = min(max(p_rul, 1e-6), 1 - 1e-6)
        ll_book.append(-(y * math.log(p_book) + (1 - y) * math.log(1 - p_book)))
        ll_ruler.append(-(y * math.log(p_rul) + (1 - y) * math.log(1 - p_rul)))
        n_used += 1
        n_fam["R%d" % rn if rn else "72H"] += 1
    conr.close()
    if verbose:
        fam = " ".join("%s=%d" % kv for kv in sorted(n_fam.items())) or "none"
        print(f"G2: {n_used} gradeable closes [{fam}] from {len(by_m)} collected matchup "
              f"markets")
        for k, v in sorted(dropped.items(), key=lambda kv: -kv[1]):
            print(f"     dropped {v:3d}  {k}")
        if n_used < 15:
            print(f"G2: n={n_used} < 15 -> gate INCONCLUSIVE. This is a FORWARD test and "
                  f"cannot be backtested: it needs OUR OWN collected closes, and the "
                  f"collector only has history from the day it started.")
        else:
            lb, lr = st.mean(ll_book), st.mean(ll_ruler)
            gap = (lr - lb) * 100
            verdict = "PASS" if gap <= 2.0 else "FAIL"
            print(f"G2 on {n_used} real FD closes: book logloss {lb:.4f}, ruler {lr:.4f} "
                  f"(gap {gap:+.1f}pts) -> {verdict}")
            # POWER-CHECKED 2026-07-30 against real out-of-sample matchup probabilities:
            # this gate fails a book 4+ pts sharper 100% of the time even at n=15, and passes
            # a book within 1 pt 100% of the time. n=15 is adequate; it was NOT a smoke test.
            # But a PASS means "within 2 pts of the book", which is equally consistent with
            # being 1.9 pts WORSE — and 1.9 pts worse, before a ~4.5% vig, loses money. G2 is
            # a SCREEN AGAINST A BROKEN MODEL, never evidence of an edge.
            print("     NOTE: PASS = 'not materially worse than the book'. It is NOT evidence "
                  "of an edge and is NOT permission to bet — that needs realized ROI/CLV on "
                  "settled flagged bets, which is a separate gate and a much larger n.")
            return verdict == "PASS", n_used
    return None, n_used


if __name__ == "__main__":
    import sys
    if "--crawl" in sys.argv:
        crawl()
    R, gsd = fit()
    top = sorted(R.items(), key=lambda kv: kv[1][0])[:8]
    print(f"ratings: {len(R)} players (global round-sd {gsd:.2f})")
    for nm, (r, s, n) in top:
        print(f"   {nm:<24} {r:+.2f} strokes/round vs field  (sd {s:.2f}, n={n})")
    if "--g2" in sys.argv:
        g2_gate()
