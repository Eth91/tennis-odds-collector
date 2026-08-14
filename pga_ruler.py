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
top-65-and-ties cut after R2 (see CUT_N).
"""
import datetime as dt
import json
import math
import unicodedata as _ud
import re
import sqlite3
import statistics as st
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "pga_model.sqlite"
LINES = HERE / "golf_lines.sqlite"
MOVES = HERE / "golf_moves.sqlite"
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
SHAPE_SLOPE = 1.30      # MEASURED 2026-07-30 on 986 runners / 9 majors with REAL closes,
                        # graded on actual finishes. Logistic slope on logit(p) fitted WITH EVENT
                        # FIXED EFFECTS so it captures SHAPE only — the per-event level is absorbed
                        # by the dummies, which matters because the backtest field is truncated to
                        # priced+rated runners and that biases level, not shape. Estimates: win
                        # 1.485 (se .310), top-20 1.527 (se .144), top-10 1.280 (se .151) — all
                        # overlapping, so ONE pooled value beats three noisy per-market slopes.
                        # >1 means our log-odds are too FLAT: the tail needs pushing down. Measured
                        # effect on the top-20 bottom quintile: .055 -> .028 (realised .010), and
                        # log-likelihood improves on both top-20 and top-10. Set to 1.0 to disable.
MIN_ROUNDS = 20         # user 2026-07-29: '20 rounds or less is a good rule'. Below
                        # this a rating is HALVED toward field-average and sigma widens
                        # — it still prices (Koivun at 46 rounds is genuinely good and
                        # unaffected), it just stops speaking with unearned confidence.

# ── CUT RULE (2026-08-13) ───────────────────────────────────────────────────────────────────
CUT_N = 65              # MEASURED over the 242 warehouse events that cut after R2 (2023-2026).
                        # "top N and ties" is NOT point-identified from results: ties make every
                        # N in (count(tot<S), count(tot<=S)] produce the SAME advancing set, so a
                        # best-fit scan just returns the smallest consistent N and the answer
                        # looks like noise spread over 40-70. The identified object is the RANGE,
                        # and the test is whether a candidate falls inside it. Share of events
                        # whose range contains the candidate: top-65 .909 · top-70 .628 ·
                        # top-60 .566 · top-50 .112. The old code used min(69, k-1) -- a top-70
                        # proxy, the PRE-2024 tour rule -- which is the worse answer in EVERY
                        # season present (2023 .676, 2024 .636, 2025 .569, 2026 .628).

# ⚠️ FIELD SIZE CANNOT SUBSTITUTE FOR THIS TABLE. Genesis/Arnold Palmer/Memorial cut at 50 with
# 69-73 starters, while Heritage/Travelers/St Jude do NOT cut at 69-72. Same size, opposite rule.
# ⚠️ AND `cut_n=None` IS NOT A COSMETIC RENAME OF THE OLD BEHAVIOUR. On a field of <=70,
# min(69, k-1) selects the LARGEST score, so everyone "made the cut" -- which is precisely why a
# wrong constant looked healthy on every playoff event. Moving to 65 without a no-cut branch
# would START eliminating players from St Jude, the BMW and the TOUR Championship.
_NO_CUT = ("fedex st jude", "st jude championship", "bmw championship", "tour championship",
           "hero world challenge", "the sentry", "sentry tournament of champions",
           "dp world tour championship", "nedbank golf challenge", "dubai invitational",
           "zozo championship", "baycurrent classic", "cadillac championship",
           "korea championship", "isps handa championship", "q school", "qschool")
# 2024 is when the tour created the signature format. Before it these were ordinary full-field
# events on the standard rule, so the era boundary is part of the rule, not a detail.
# (pattern, first season the event stopped cutting). Pebble Beach is 2025, not 2024: in
# 2023-24 it was still a 54-hole-cut pro-am, so a single shared boundary gets it wrong.
_NO_CUT_SINCE = (("rbc heritage", "2024"), ("travelers championship", "2024"),
                 ("truist championship", "2024"), ("wells fargo", "2024"),
                 ("abu dhabi hsbc", "2024"), ("pebble beach", "2025"))
_CUT_50 = (("masters tournament", None), ("genesis invitational", "2024"),
           ("arnold palmer", "2024"), ("memorial tournament", "2024"))
# EXACT normalised match only: "BMW PGA Championship" and "BMW Australian PGA Championship" are
# ordinary 65 events, and "Genesis Scottish Open" must not match "the open".
_CUT_70 = ("pga championship", "the open")
# ⚠️ TWO DIFFERENT EVENTS, ONE NORMALISED NAME. "ISPS Handa Championship" (2023, 72
# players, no cut) and "ISPS HANDA - CHAMPIONSHIP" (2024, 155 players, cuts) collapse to
# the same string, so no name table can separate them -- only the field size can. The
# guard is deliberately scoped to this one pattern: a general "no-cut events are small"
# rule is FALSE, because Q-School is a genuine 170-player no-cut event.
_NO_CUT_AMBIGUOUS = ("isps handa championship",)
NO_CUT_MAX_FIELD = 100


def _get(url):
    return json.load(urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=40))


def crawl(seasons=(2023, 2024, 2025, 2026), leagues=("pga", "eur")):
    """Season scoreboards -> rounds(player, event, date, round, score). Idempotent.

    leagues: ESPN golf league slugs. Defaults to PGA + DP World, chosen on MEASURED 2025 player
    overlap with the PGA field — eur shares 248 players (30% of its field), champions-tour only 21
    (7%), and lpga ZERO. The two-pass field-quality correction calibrates tours against each other
    only through shared players, so a disjoint tour would get ratings on an uncalibrated scale that
    look comparable and are not. eur is the one safe addition.
    """
    con = sqlite3.connect(DB, timeout=60)
    con.execute("""CREATE TABLE IF NOT EXISTS rounds(
        event_id TEXT, event TEXT, date TEXT, player TEXT, rnd INTEGER, score REAL,
        PRIMARY KEY(event_id, player, rnd))""")
    for yr in seasons:
      for _lg in leagues:
        try:
            d = _get("https://site.web.api.espn.com/apis/site/v2/sports/golf/%s/scoreboard?dates=%d"
                     % (_lg, yr))
        except Exception:                                          # noqa: BLE001
            continue                                               # a tour missing a season is fine
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
    con = sqlite3.connect(DB, timeout=60)
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
        con = sqlite3.connect(DB, timeout=60)
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


_STROKES = str.maketrans({"ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D",
                          "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ß": "ss",
                          "þ": "th", "Þ": "TH", "ð": "d", "Ð": "D"})


def _deaccent(s):
    """Strip combining marks so "Åberg" and "Aberg" are the same player.

    NFKD ALONE IS NOT ENOUGH, and that is the trap. "ø" is not an "o" carrying a combining mark — it
    is its own Latin letter (U+00F8), so NFKD leaves it untouched and Højgaard/Hojgaard survived the
    first version of this fix as two different players. Same for ł, đ, æ, ß, þ, ð. They need an
    explicit translation applied BEFORE the decomposition. Scandinavian names are common in this
    field, so this is the case that matters most here, not an edge case.

    VERIFIED SAFE before shipping: applied across all 2,459 rated warehouse names this produces
    exactly one collision, and it is the same player spelled two ways
    ("gonzalo fdez-castano" / "gonzalo fdez-castaño"). No two distinct players merge. That check is
    the whole justification — a normaliser that merges two real players does more damage than one
    that splits one, so the direction of the risk had to be measured, not assumed.
    """
    return "".join(c for c in _ud.normalize("NFKD", s.translate(_STROKES))
                   if not _ud.combining(c))


def norm(n):
    return " ".join(_deaccent(str(n or "")).lower().replace(".", "").split())


def resolve(name, candidates):
    """Map a book/feed name onto a known player. Returns the matching normalised key, or None.

    STRICTLY A FALLBACK. Exact normalised equality is tried first, so this can never redirect a name
    that already matches — it can only rescue one that currently resolves to nothing and is
    therefore silently dropped as "unrated".

    The fallback is surname + first initial, and ONLY when that is UNIQUE among the candidates.
    That covers the nickname family (Matt/Matthew Fitzpatrick, Chris/Christopher Gotterup,
    Alex/Alexander Norén, Rico/Richard Hoey, Cam/Cameron Davis) without a hand-maintained alias
    list, which would rot silently the first time a new player arrived. Ambiguity returns None
    rather than guessing: an unmatched player is a visible gap, a WRONGLY matched one is a bet
    priced off somebody else's record.
    """
    k = norm(name)
    cand = {norm(c) for c in candidates}
    if k in cand:
        return k
    parts = k.split()
    if len(parts) < 2:
        return None
    surname, initial = parts[-1], parts[0][:1]
    hits = {c for c in cand
            if c.split()[-1:] == [surname] and c.split()[0][:1] == initial}
    return hits.pop() if len(hits) == 1 else None


def _evnorm(s):
    return " ".join("".join(c if c.isalnum() else " "
                            for c in _deaccent(str(s or "")).lower()).split())


def cut_rule(event, date=None, n_field=None):
    """Cut size for `event` as of `date`: 65 (standard), 50, 70, or None for a no-cut event.

    Unrecognised names get the default 65. That is the right prior -- 242 of the 296 warehouse
    events cut after R2 and 90.9% of those are consistent with 65 -- and an unknown name is far
    likelier to be an ordinary full-field stop than a playoff.

    ⚠️ THE COST OF BEING WRONG IS ASYMMETRIC. Calling a no-cut event a cutting one ELIMINATES
    players who never faced a cut and zeroes their top-N and win probabilities outright; the
    reverse merely leaves a few extra players in the last two rounds. Every no-cut family on
    tour is enumerated above for that reason, and the default leans the safe way only because
    a full-field event is the overwhelming base case.

    `date=None` means "now", so the era-dependent entries resolve to their CURRENT rule.
    """
    n = _evnorm(event)
    if not n:
        return CUT_N
    yr = str(date)[:4] if date else None

    def _guard(pat):
        # Only for the known-colliding name; everything else is trusted as written.
        if pat in _NO_CUT_AMBIGUOUS and n_field and int(n_field) > NO_CUT_MAX_FIELD:
            return CUT_N
        return None
    for pat in _CUT_70:
        if n == pat or n == pat + " championship":
            return 70
    for pat in _NO_CUT:
        if pat in n:
            return _guard(pat)
    for pat, since in _NO_CUT_SINCE:
        if pat in n and (yr is None or yr >= since):
            return None
    for pat, since in _CUT_50:
        if pat in n and (since is None or yr is None or yr >= since):
            return 50
    return CUT_N


# Fitted 2026-08-13 on 166 walk-forward events (<2026), holdout 2026 untouched, via the LL-optimal
# stretch through _recal_shape itself -- the same estimand 1.30 was chosen by. Holdout: beats 1.30
# on 8/8 markets. Majors are deliberately absent: their fitted values LOSE to 1.30 out of sample.
SHAPE_SLOPE_STD = {"win": 1.21, "win_ties": 1.02,
                   "top5": 1.03, "top5_ties": 1.03,
                   "top10": 1.00, "top10_ties": 1.00,
                   "top20": 1.00, "top20_ties": 1.01}

# EXACT normalised match only -- "BMW PGA Championship" is NOT a major, and neither is
# "Genesis Scottish Open". Same collision class as the cut-rule table above.
_MAJOR_NAMES = ("masters tournament", "pga championship", "us open", "u s open",
                "the open", "the open championship", "us open championship")


def is_major(event):
    """True only for the four majors. Deliberately strict: a false positive here silently
    applies the 1.30 majors stretch to an ordinary event, which is the defect being fixed."""
    n = _evnorm(event)
    if not n:
        return False
    for tok in ("pga tour", "dp world", "korn ferry", "lpga", "bmw", "australian", "senior"):
        if tok in n and "masters tournament" not in n:
            if tok in ("bmw", "australian", "senior", "lpga"):
                return False
    return any(n == m or n.endswith(" " + m) or n.startswith(m + " ") or
               (" %s " % m) in (" %s " % n) for m in _MAJOR_NAMES)


def shape_slopes(event, date=None):
    """Per-market stretch for `event`: the fitted non-major table, or None to mean 'use
    SHAPE_SLOPE for everything' (majors). Returning None rather than a dict of 1.30s keeps the
    majors path byte-identical to what shipped before this change."""
    return None if is_major(event) else dict(SHAPE_SLOPE_STD)


# ── RANK-CONDITIONAL PLACEMENT OFFSETS (2026-08-14) ────────────────────────────────────────
# Logit offsets by the model's OWN win-rank bucket, fitted 2023-25 and validated on the 2026
# holdout. Buckets: rank 1 | 2-5 | 6-15 | 16-40 | 41+. Positive lifts, negative shrinks.
# The shape is stable across all six markets, which is what says structure rather than noise.
RANK_EDGES = (1, 2, 6, 16, 41)
RANK_OFFSETS = {
    "top5":       (+0.710, +0.270, +0.260, -0.040, -0.260),
    "top10":      (+0.700, +0.320, +0.350, +0.050, -0.220),
    "top20":      (+0.670, +0.360, +0.290, +0.040, -0.180),
    "top5_ties":  (+0.690, +0.270, +0.270, +0.010, -0.240),
    "top10_ties": (+0.720, +0.310, +0.340, +0.030, -0.200),
    "top20_ties": (+0.690, +0.310, +0.240, +0.010, -0.200),
}
# win / win_ties are DELIBERATELY ABSENT: the same offsets make the win holdout worse.


def _rank_bucket(rank):
    b = 0
    for i, e in enumerate(RANK_EDGES):
        if rank >= e:
            b = i
    return b


def _recal_rank(out, keys):
    """Apply the win-rank offsets, re-solving one intercept per key so the FIELD TOTAL holds.

    Same sum-preserving contract as _recal_shape: shape changes, coherence does not. Without it
    the placement probabilities stop summing to 5/10/20 and every downstream devig is wrong.
    """
    if not out:
        return out
    players = list(out)
    ranked = sorted(players, key=lambda p: -((out[p] or {}).get("win") or 0.0))
    bucket = {p: _rank_bucket(i + 1) for i, p in enumerate(ranked)}
    for key in keys:
        offs = RANK_OFFSETS.get(key)
        if not offs:
            continue                      # win / win_ties fall through untouched, by design
        vals = [(p, (out[p] or {}).get(key)) for p in players]
        vals = [(p, v) for p, v in vals if v is not None]
        if len(vals) < 10:
            continue
        target = sum(v for _p, v in vals)
        if target <= 0:
            continue
        lg = []
        for p, v in vals:
            q = min(max(v, 1e-9), 1 - 1e-9)
            lg.append((p, math.log(q / (1 - q)) + offs[bucket[p]]))
        lo, hi = -40.0, 40.0
        for _ in range(60):
            c = (lo + hi) / 2.0
            if sum(1.0 / (1.0 + math.exp(-(l + c))) for _p, l in lg) > target:
                hi = c
            else:
                lo = c
        c = (lo + hi) / 2.0
        for p, l in lg:
            out[p][key] = 1.0 / (1.0 + math.exp(-(l + c)))
    return out


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


def _recal_shape(out, keys, slope=None):
    """Stretch each probability's log-odds by `slope`, preserving the field total exactly.

    The total is what makes these numbers coherent — win sums to 1, top20 to 20, and the
    ties-inclusive variants to their own (larger) totals. So rather than renormalising to a
    nominal N, this re-solves a single additive intercept per key so the NEW sum equals the OLD
    sum. Shape changes; coherence does not.
    """
    sl = SHAPE_SLOPE if slope is None else slope
    if not out:
        return out
    # `slope` may be a per-market dict (regime split) or a single float (legacy / majors).
    if not isinstance(sl, dict) and abs(sl - 1.0) < 1e-9:
        return out
    for key in keys:
        s_key = sl.get(key, SHAPE_SLOPE) if isinstance(sl, dict) else sl
        if abs(s_key - 1.0) < 1e-9:
            continue
        ps = [(out[p_] or {}).get(key) for p_ in out]
        ps = [v for v in ps if v is not None]
        if len(ps) < 10:
            continue
        target = sum(ps)
        if target <= 0:
            continue
        lg = []
        for p_ in out:
            v = (out[p_] or {}).get(key)
            lg.append(None if v is None
                      else math.log(min(max(v, 1e-9), 1 - 1e-9) / (1 - min(max(v, 1e-9), 1 - 1e-9))))
        lo, hi = -40.0, 40.0
        for _ in range(200):
            c = (lo + hi) / 2.0
            tot = sum(1.0 / (1.0 + math.exp(-(s_key * l + c))) for l in lg if l is not None)
            if tot > target:
                hi = c
            else:
                lo = c
        c = (lo + hi) / 2.0
        for p_, l in zip(list(out), lg):
            if l is not None:
                out[p_][key] = 1.0 / (1.0 + math.exp(-(s_key * l + c)))
    return out


def simulate(R, field, n_sims=8000, seed=7, course_fit=None, wave=None,
             wave_shift=0.0, progress=None, partial=None, reps=1, cut_n=CUT_N,
             shape_slope=None):
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
                           progress=progress, partial=partial, reps=1, cut_n=cut_n,
                           shape_slope=shape_slope)
            if not one:
                return {}
            for pl, v in one.items():
                a = acc.setdefault(pl, {})
                for k_, val in v.items():
                    a[k_] = a.get(k_, 0.0) + val / float(reps)
        return acc
    """Win/top5/10/20/make-cut probs via MC: 4 rounds, player-week effect, `cut_n` cut."""
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
    # NO-CUT EVENTS AND SHORT FIELDS: `cut_n=None` is a playoff/limited-field event, and
    # k <= cut_n means top-N-and-ties admits the whole field anyway. Both must short-circuit
    # BEFORE the index, or a 50-man TOUR Championship reads tot2[:, 64] and dies.
    if cut_n is None or k <= int(cut_n):
        made = np.ones(tot2.shape, dtype=bool)
    else:
        # 'and ties': the line is the cut_n-th best 36-hole total and <= admits every tie.
        cutline = np.sort(tot2, axis=1)[:, int(cut_n) - 1][:, None]
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
    # TAIL RECALIBRATION (2026-07-30). Skipped in-play: SHAPE_SLOPE was fitted on pre-tournament
    # sims, and once posted scores condition the distribution it is already sharp — stretching it
    # would distort a number that is no longer a forecast of 4 unknown rounds.
    if progress is None and partial is None:
        # RANK OFFSETS FIRST, then the global stretch. The offsets were fitted on unstretched
        # probabilities, so applying them after the stretch would fit one correction on top of
        # another's output and neither would mean what it was measured to mean.
        _recal_rank(out, ("top5", "top10", "top20",
                          "top5_ties", "top10_ties", "top20_ties"))
        _recal_shape(out, ("win", "top5", "top10", "top20",
                           "win_ties", "top5_ties", "top10_ties", "top20_ties"),
                     slope=shape_slope)
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
    con = sqlite3.connect(DB, timeout=60)
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
        con = sqlite3.connect(DB, timeout=60)
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
    con = sqlite3.connect(DB, timeout=60)
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


_TEE_CACHE = {}


def _tee_deadline(evn, mkt):
    """Actual tee-time deadline for a matchbet market, or None if it cannot be resolved.

    ⚠️ A DATE IS NOT A DEADLINE. g2_gate used to cut on `str(ts)[:10] > event_date`, which
    admits EVERY price stamped on the round's own day -- and the round tees off in the middle
    of that day. On 2026-08-13 the Kitayama/Fowler R1 matchbet sat flat at 1.9091/1.8333 until
    the 14:25 tee, then drifted 1.53 -> 1.13 -> 1.0033 as Kitayama played, and the gate scored
    the 18:00 price of 1.002/26.0 as a "close". The book was not sharp; it was watching golf.
    That single class of row took G2 from book LL .6782 (PASS, +1.8pts) to .6296 (FAIL, +6.7pts)
    on four rows out of 51 -- their book log-loss was 0.058 against a ruler at 0.704.

    This is the SAME defect the docstring already claims to have fixed ("it used to be
    MAX(collected_at), which during a live event is an IN-PLAY price"). The fix went to date
    granularity and stopped there, so it still fires on any round being played today.
    """
    key = (evn, mkt)
    if key in _TEE_CACHE:
        return _TEE_CACHE[key]
    out = None
    try:
        import pga_tee_gate as _TG
        d = _TG.deadline(evn, mkt)
        d = d[0] if isinstance(d, tuple) else d      # deadline() returns (dt, reason)
        if isinstance(d, dt.datetime):
            out = d
    except Exception:                                                  # noqa: BLE001
        out = None
    _TEE_CACHE[key] = out
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
    # ⚠️ golf_lines IS A 2-DAY ROLLING BUFFER. Reading the gate off it alone meant a completed
    # event's matchups were PRUNED long before its results landed, so the gate could only ever
    # see markets whose outcome did not exist yet -- n stayed 0 permanently and NOT ONE FLAG
    # HAS EVER ARMED. That is not "give it time"; it was structurally unreachable.
    # golf_moves is the durable, write-once store built for exactly this: one row per
    # (event, market, runner) carrying the CLOSE as the last price before that round's tee,
    # with the deadline already resolved through pga_tee_gate. Read it FIRST, then union the
    # live buffer so an event still in progress is not missed. Overlap is harmless: the
    # per-runner selection below keeps the latest quote before the cutoff either way.
    raw = []
    try:
        cm = sqlite3.connect(MOVES, timeout=60)
        raw += cm.execute(
            "SELECT event, market, runner, close_odds, close_ts FROM moves "
            "WHERE market LIKE '%Matchbet%' AND close_odds > 1.0 "
            "AND close_ts IS NOT NULL").fetchall()
        cm.close()
    except sqlite3.Error as _me:
        print(f"G2: golf_moves unreadable ({str(_me)[:50]}) — live buffer only")
    con = sqlite3.connect(LINES, timeout=60)
    raw += con.execute(
        "SELECT event, market, runner, odds, collected_at FROM golf_lines "
        "WHERE market LIKE '%Matchbet%' AND odds > 1.0").fetchall()
    con.close()
    by_m = defaultdict(list)
    for evn, mkt, run, od, ts in raw:
        by_m[(str(evn).strip(), mkt)].append((run, od, ts))
    conr = sqlite3.connect(DB, timeout=60)
    ll_book, ll_ruler, n_used = [], [], 0
    ll_flat, edge_ruler, ev_used = [], [], set()
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
        # TEE-TIME CUTOFF (2026-08-13). Prefer the resolved tee; fall back to the DATE only
        # for rows stamped strictly BEFORE the round's day. When the tee is unknown a same-day
        # row is refused outright -- not knowing when the round started is not permission to
        # treat a price from that day as a close.
        _dl = _tee_deadline(evn, mkt)
        best = {}
        for run, od, ts in quotes:
            if _dl is not None:
                try:
                    _t = dt.datetime.fromisoformat(str(ts).replace("Z", ""))
                except ValueError:
                    dropped["unparseable timestamp"] += 1
                    continue
                if _t >= _dl:
                    continue             # in-play or post-round: not a close
            elif str(ts)[:10] >= cutoff.isoformat():
                continue                 # tee unknown: refuse the round's own day entirely
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
        # PLACEBO: a model with NO information. If the ruler cannot beat this, "within 2 pts of
        # the book" is being achieved by having no opinion rather than by being right.
        ll_flat.append(math.log(2.0))
        edge_ruler.append(abs(p_rul - 0.5))
        ev_used.add(eid)
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
            lf = st.mean(ll_flat)
            gap = (lr - lb) * 100
            plac = (lf - lr) * 100          # >0 means the ruler beats a coin flip
            # TWO conditions now. The ceiling (near the book) was always necessary; the FLOOR
            # (better than no information) is what was missing, and it is the one the model fails.
            verdict = "PASS" if (gap <= 2.0 and plac >= 0.0) else "FAIL"
            _sp = st.mean(edge_ruler) if edge_ruler else 0.0
            print(f"G2 on {n_used} real FD closes from {len(ev_used)} EVENTS: "
                  f"book {lb:.4f}, ruler {lr:.4f}, coin-flip {lf:.4f} "
                  f"(vs book {gap:+.1f}pts, vs placebo {plac:+.1f}pts) -> {verdict}")
            if plac < 0.0:
                print(f"     ❌ THE RULER IS WORSE THAN A COIN FLIP ({-plac:.1f}pts). Its mean "
                      f"|p-0.5| is {_sp:.4f} against a ~6% hold — it is functionally a constant, "
                      f"so 'within 2pts of the book' is being cleared by having NO OPINION. "
                      f"A near-book log-loss earned this way is not evidence of anything.")
            if len(ev_used) < 30:
                print(f"     ⚠️ n={n_used} closes but only {len(ev_used)} EVENTS. Closes inside "
                      f"one tournament share weather, course and field, so the sample size is "
                      f"the EVENT count. Every SE here is optimistic; do not arm on this.")
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
