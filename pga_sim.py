"""⛳ PGA TOURNAMENT SIMULATOR — one explicit generative model, one free parameter.

THE MODEL (exactly as specified; nothing else is in here)

    score[p, r] = mean[p] + sigma[p] * z[p, r] + TAU * w[r]

      p = player, r = round 1..4
      z[p, r] ~ N(0, 1)   independent across players AND rounds
      w[r]    ~ N(0, 1)   ONE draw per round, SHARED by the whole field
      TAU     = the only free parameter (module constant, default 1.0)

`mean[p]` and `sigma[p]` are taken from `pga_ruler.fit(asof=<event start>)` and are NEVER
refit here. HALF_LIFE_D=270 / K_SHRINK=11 / SIG_SHRINK=78 were tuned on 2024-25 with 2026
held out; this module reads their output and does not touch them. `ratings_asof()` is the
one place that reads the ratings DB, and it is a read-only delegate to `pga_ruler.fit`.

UNITS AND SIGN. Everything is STROKES PER ROUND RELATIVE TO THE FIELD MEAN, and NEGATIVE IS
BETTER (lower score wins). A rating of -1.8 means "1.8 strokes per round better than the
field average of the events he played". `baseline=` shifts reported scores into absolute
strokes for display; it changes no probability.

⚠️ TWO PROPERTIES OF THIS MODEL THE CALIBRATION STEP MUST KNOW ABOUT
  1. `TAU * w[r]` is a COMMON additive shift: every player in the field gets the SAME number
     added in round r. Every market this simulator prices — win, top-N, make-cut, leader — is
     a RANK statistic, and a common shift cancels out of ranks exactly. So TAU is very nearly
     UNIDENTIFIED from win/top-N/cut probabilities. Its only residual effect is through
     integer rounding (a common real-valued shift moves each player's rounding boundary
     differently, which perturbs the TIE structure at the 0.1-0.3pp level). `tau_sensitivity()`
     measures this directly — run it before spending compute fitting TAU on rank outcomes.
     TAU *does* move absolute quantities: winning score, per-round score spread, cut line.
  2. `sigma[p]` from `pga_ruler.fit` is the sd of (score - that round's FIELD MEAN), so any
     common per-round conditions effect has ALREADY been differenced out of it. Adding
     `TAU * w[r]` therefore ADDS variance rather than re-attributing it: per-round total
     variance becomes sigma^2 + TAU^2 (2.80 -> 2.97 sd at TAU=1.0). That is correct if you
     want ABSOLUTE scores, and it is double counting if you calibrate TAU against the
     realised spread of field-relative scores.

WHAT THIS MODULE DOES NOT DO — read this before trusting a number out of it:
  * no course fit, no wave / tee-time split, no weather, no wind, no player-week form effect
    (pga_ruler's RHO), no SPREAD widening by default, no tail recalibration (SHAPE_SLOPE),
    no in-play conditioning on posted scores, no withdrawals, no playoff format;
  * no network calls and no writes of any kind — `simulate()` never touches disk;
  * it does not price anything. It emits probabilities. Devigging, blending and edge gating
    live in pga_e3.py and are deliberately not duplicated here.

CUT RULE — VERIFIED, NOT ASSUMED. Against all 248 cut events in pga_model.sqlite, comparing
each event's observed set of round-3 starters to what each rule predicts from the 36-hole
totals:
        season   n     top-65-and-ties   top-70-and-ties
        2023     70        0.900              0.657
        2024     67        0.896              0.627
        2025     67        0.910              0.552
        2026     44        0.818              0.614
Top-65-and-ties is the default. (pga_ruler.simulate uses a top-70 proxy — `min(69, k-1)` —
which is the PRE-2024 tour rule and is wrong for 3 of the 4 seasons in the warehouse.) The
residual disagreements are the known exceptions and are NOT auto-detected here: signature
events cut top-50-and-ties (Genesis, Arnold Palmer, Memorial), the Masters top-50-and-ties,
the PGA Championship and The Open top-70-and-ties. Pass `cut_n=` for those.
NO-CUT EVENTS: the FedEx Cup playoffs have no 36-hole cut — verified in the warehouse, all
70/70/69 starters played four rounds at the 2023/2024/2025 FedEx St. Jude Championship.
Pass `cut_n=None`; the simulator will NOT infer it from field size.

FIELD HYGIENE — THREE WAYS A FIELD LIST LIES, ALL OF THEM SURFACED, NONE SILENT
  * `unrated`   : a name no rating could be found for. DROPPED (the field is smaller).
  * `duplicates`: two entries that resolve to the SAME rating record — "Matt Fitzpatrick" and
                  "Matthew Fitzpatrick", "Ludvig Aberg" and "Ludvig Åberg". Exactly the
                  nickname family `pga_ruler.resolve` exists to fold, and exactly what you get
                  when two book feeds are merged. Simulating both would put one man in the
                  field twice and dilute EVERY other player's win% by roughly 1/k. The second
                  entry is DROPPED and the pair is reported.
  * `collisions`: two RATINGS keys that fold to one after normalisation (see `_index`).
  A duplicate LITERAL name that somehow survives to the simulator raises — the per-player
  result dicts are keyed by name, so duplicates would silently lose a player and the
  probabilities would stop summing to 1.

DETERMINISM. Given (seed, n, chunk) the output is bit-identical, in-process and across
processes, and independent of PYTHONHASHSEED and thread counts. `chunk` only exists to cap
peak memory and defaults to a module constant, so ordinary calls are reproducible from
(seed, n) alone; changing `chunk` changes the random stream and therefore the answer at
Monte-Carlo noise level — a paired A/B MUST hold `chunk` (and the field, which sets the draw
shape) fixed. `seed=None` draws a fresh OS seed and RECORDS it on the result as `.seed`, so
any run can be replayed. `cut_ties=False` draws one extra uniform per (sim, player) to break
cut-line ties AT RANDOM; that draw happens inside the branch, so the default `cut_ties=True`
stream is unaffected by its existence.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np

# ---------------------------------------------------------------- constants
TAU = 1.0            # THE only free parameter. Strokes of shared per-round conditions.
                     # Fitted by a separate calibration step; see the two warnings above.
CUT_N = 65           # top-65-and-ties, VERIFIED above. None = no cut.
CHUNK_SIMS = 2500    # sims per block. Caps peak memory at ~2x (chunk, k, 4) float64 (the
                     # normal draw plus the score array before rounding) — ~24 MB at k=150,
                     # measured peak RSS ~84 MB for the whole run. 2500 is also the fastest of
                     # {1000, 2500, 5000, 10000} on the board VM: bigger blocks fall out of
                     # cache and get SLOWER, so "raise it to go faster" is wrong here.
_HIST_LO, _HIST_HI = -30, 30      # per-round score histogram support, field-relative strokes
_NROUNDS = 4

# A rating this far out is a data error, not a golfer: |mean| or sigma beyond it would push
# round scores outside the histogram support and can make the rank bincount ask for terabytes.
# Refused by name in `_check_ratings` rather than clipped, cast to garbage, or MemoryError'd.
MAX_ABS_RATING = 30.0             # strokes per round
_MAX_RANK_SPAN = 100_000          # max integer span of 72-hole totals `_rank_counts` will bin


# ---------------------------------------------------------------- name handling
def _norm(name):
    """Normalise a player name for lookup, delegating to pga_ruler so there is ONE normaliser.

    Falls back to a plain lower/strip if pga_ruler cannot be imported, which keeps this module
    importable standalone. Does NOT do fuzzy matching — see `_index`.
    """
    try:
        import pga_ruler as RU
        return RU.norm(name)
    except Exception:                                                        # noqa: BLE001
        return " ".join(str(name or "").lower().replace(".", "").split())


COLLISION_TOL = 0.50    # strokes/round. Above this, two colliding names are treated as two
                        # DIFFERENT players and the lookup refuses rather than guessing.


def _index(ratings):
    """({normalised name -> key in `ratings`}, [collisions]) — collisions are surfaced, never silent.

    pga_ruler.norm folds accents and punctuation, which is what lets a book's "Ludvig Aberg"
    find the warehouse's "Ludvig Åberg". Across the 2,460 warehouse names it produces exactly
    ONE collision and it is one player spelled two ways ("Gonzalo Fdez-Castano" /
    "Gonzalo Fdez-Castaño"). When a collision happens the entry with MORE rated rounds wins
    (ties broken lexicographically, so the choice is deterministic), and the pair is returned
    so the caller can print it — a merged name must be visible, not inferred from a gap.

    RAISES if the colliding entries differ by more than COLLISION_TOL strokes/round, which
    means they are not the same player and picking either would price a bet off the wrong
    record. Does NOT do fuzzy matching — that is `pga_ruler.resolve`, used by `lookup`.
    """
    idx, coll = {}, []
    for key in sorted(ratings):
        n = _norm(key)
        prev = idx.get(n)
        if prev is None:
            idx[n] = key
            continue
        a, b = ratings[prev], ratings[key]
        if abs(float(a[0]) - float(b[0])) > COLLISION_TOL:
            raise ValueError(
                f"name collision after normalisation between DIFFERENT records: "
                f"{prev!r} (mean {float(a[0]):+.2f}) vs {key!r} (mean {float(b[0]):+.2f}); "
                f"they differ by more than COLLISION_TOL={COLLISION_TOL} strokes/round, so "
                f"they are not the same player — fix the source names, do not merge them")
        coll.append((prev, key))
        na = int(a[2]) if len(a) > 2 else 0
        nb = int(b[2]) if len(b) > 2 else 0
        if nb > na:
            idx[n] = key
    return idx, coll


def lookup_key(ratings, name, idx=None):
    """(canonical ratings key, (mean, sigma[, n])) for `name`, or (None, None) if unknown.

    Exact key, then normalised key, then `pga_ruler.resolve`'s surname+initial fallback (which
    only fires when the match is UNIQUE — an ambiguous name comes back None, a visible gap,
    rather than being resolved to somebody else's record).

    THE KEY IS THE POINT. Two different field spellings of one player — "Matt Fitzpatrick" and
    "Matthew Fitzpatrick", "Ludvig Aberg" and "Ludvig Åberg" — both land on the SAME canonical
    key, which is how `field_ratings` can tell them apart from two different men. The key is
    canonicalised through `_index`, so even two ratings keys that fold together (the
    Fdez-Castaño pair) report as one identity.
    Pass `idx` from `_index` to avoid rebuilding it per name over a 150-player field.
    Does NOT handle transliteration beyond what pga_ruler.norm covers.
    """
    if idx is None:
        idx, _ = _index(ratings)
    key = None
    if name in ratings:
        key = name
    else:
        n = _norm(name)
        if n in idx:
            key = idx[n]
        else:
            try:
                import pga_ruler as RU
                hit = RU.resolve(name, list(ratings.keys()))
            except Exception:                                                # noqa: BLE001
                hit = None
            if hit and hit in idx:
                key = idx[hit]
    if key is None:
        return None, None
    key = idx.get(_norm(key), key)          # canonicalise a folded pair onto one identity
    return key, ratings[key]


def lookup(ratings, name, idx=None):
    """The (mean, sigma[, n]) tuple for `name`, or None. Thin wrapper over `lookup_key`.

    Does NOT tell you WHICH record matched — use `lookup_key` when you need to detect two
    field entries landing on one player.
    """
    return lookup_key(ratings, name, idx=idx)[1]


# ---------------------------------------------------------------- ratings (the ONE impure fn)
def ratings_asof(asof, rows=None):
    """A PAIR: ({player: (mean, sigma, n_rounds)}, g_sd) as of `asof` (YYYY-MM-DD), READ ONLY.

    ⚠️ IT RETURNS TWO THINGS, not the mapping alone. `simulate(field, ratings=ratings_asof(d))`
    is wrong and dies deep inside `_index`; unpack it:
        ratings, g_sd = ratings_asof("2026-08-01")

    THE ONLY FUNCTION HERE THAT TOUCHES THE OUTSIDE WORLD. It opens pga_model.sqlite for
    reading via `pga_ruler.fit` and returns a plain dict; nothing is written and nothing is
    refit — the frozen constants (HALF_LIFE_D=270, K_SHRINK=11, SIG_SHRINK=78, MIN_ROUNDS=20)
    are left at their module defaults on purpose.

    `asof` is STRICT: only rounds with date < asof are used, so passing the event's own start
    date is leak-free. Pass `rows=pga_ruler.all_rows()` to avoid re-querying across many
    as-of dates.

    Does NOT handle: fetching new results (no crawl), course fit, or field selection.
    """
    import pga_ruler as RU
    R, g_sd = RU.fit(asof=asof, rows=rows)
    return {k: (float(v[0]), float(v[1]), int(v[2])) for k, v in R.items()}, float(g_sd)


def field_ratings(players, ratings, spread=1.0):
    """(names, mean[], sigma[], unrated[], collisions[], duplicates[]) for `players`.

    `spread` widens each rating's DEVIATION FROM THIS FIELD'S MEAN by that factor before it is
    used, matching pga_ruler.SPREAD. Default 1.0 = OFF, i.e. the literal model in the header.
    pga_ruler prices with 1.30 because K_SHRINK-shrunk point estimates make a field look too
    homogeneous once you put them through a non-linear rank simulation; at 1.0 this simulator
    will be visibly FLATTER than pga_e3's numbers. That is expected, not a bug.

    Does NOT handle unrated players: they are returned in `unrated` and DROPPED from the sim.
    A dropped player still changes everyone else's probabilities (the field is smaller), so
    check `unrated` before believing a top-N number.

    DUPLICATE ENTRIES ARE DROPPED, NOT SIMULATED TWICE. Two field strings that resolve to the
    same rating record are the same man — the FIRST spelling is kept and each later one is
    returned in `duplicates` as (kept, dropped, key). Letting both through would enter one
    player as two independent competitors: measured on a 6-man field, one duplicated
    Fitzpatrick cost every rival ~10-13% of their win probability and invented a phantom
    11% winner, with `unrated` and `collisions` both empty. The dilution is ~1/k, so at a
    156-man field it is ~3% — small, invisible, and wrong in the same direction every time.
    """
    idx, collisions = _index(ratings)
    names, mu, sg, unrated, duplicates = [], [], [], [], []
    seen = {}
    for p in players:
        key, v = lookup_key(ratings, p, idx=idx)
        if v is None:
            unrated.append(p)
            continue
        if key in seen:
            duplicates.append((seen[key], p, key))
            continue
        seen[key] = p
        names.append(p)
        mu.append(float(v[0]))
        sg.append(float(v[1]))
    mu = np.asarray(mu, dtype=np.float64)
    sg = np.asarray(sg, dtype=np.float64)
    if len(mu) and spread != 1.0:
        fm = float(mu.mean())
        mu = fm + float(spread) * (mu - fm)
    return names, mu, sg, unrated, collisions, duplicates


def _check_ratings(names, mu, sg, tau):
    """Refuse non-finite / negative / absurd ratings BY NAME, before they reach the RNG.

    Exists because the failure modes downstream are all silent-or-useless: `np.rint(nan)` cast
    to int32 is undefined behaviour (it lands on INT32_MIN here), which then asks `_rank_counts`
    for a 3.13 TiB bincount and dies with a MemoryError naming neither the player nor the field;
    a negative sigma quietly mirrors z and returns plausible-looking probabilities; a mean of
    -40 silently piles onto the edge bin of the score histogram.
    """
    bad = []
    for i, p in enumerate(names):
        m, s = float(mu[i]), float(sg[i])
        if not (math.isfinite(m) and math.isfinite(s)):
            bad.append(f"{p!r}: mean={m}, sigma={s} (not finite)")
        elif s < 0.0:
            bad.append(f"{p!r}: sigma={s:+.3f} (negative — sigma is an SD, not a variance)")
        elif abs(m) > MAX_ABS_RATING or s > MAX_ABS_RATING:
            bad.append(f"{p!r}: mean={m:+.3f}, sigma={s:.3f} "
                       f"(outside +/-{MAX_ABS_RATING:g} strokes/round)")
    if not (math.isfinite(tau) and 0.0 <= tau <= MAX_ABS_RATING):
        bad.append(f"tau={tau} (must be finite and in [0, {MAX_ABS_RATING:g}])")
    if bad:
        head = "; ".join(bad[:8])
        more = f" ... and {len(bad) - 8} more" if len(bad) > 8 else ""
        raise ValueError(f"unusable rating(s) — the simulator refuses to guess: {head}{more}")


# ---------------------------------------------------------------- rank helper
def _rank_counts(tot, alive):
    """(n_strictly_better, n_tied_with) per (sim, player) for INTEGER totals; lower is better.

    Dead (cut/eliminated) players are parked on a sentinel worse than every live score so they
    can never pollute a live player's rank, and their own counts are meaningless — mask them.
    Uses a per-row bincount rather than an (n, k, k) pairwise comparison, which at k=150 would
    be 100x the memory.
    """
    m, k = tot.shape
    t = tot.astype(np.int64, copy=True)
    if alive is not None and not alive.all():
        live_max = int(t[alive].max()) if alive.any() else 0
        t = np.where(alive, t, live_max + 1)
    lo = int(t.min())
    idx = t - lo
    M = int(idx.max()) + 1
    if M > _MAX_RANK_SPAN:
        raise ValueError(
            f"72-hole totals span {M} strokes ({lo} to {lo + M - 1}), over the "
            f"_MAX_RANK_SPAN={_MAX_RANK_SPAN} guard; the bincount would need "
            f"{m * M * 8 / 2**30:.1f} GiB. Some rating is nonsense — check `mean`/`sigma`")
    flat = (idx + (np.arange(m, dtype=np.int64) * M)[:, None]).ravel()
    cnt = np.bincount(flat, minlength=m * M).reshape(m, M)
    cum = np.cumsum(cnt, axis=1)
    n_le = np.take_along_axis(cum, idx, axis=1)
    n_eq = np.take_along_axis(cnt, idx, axis=1)
    return n_le - n_eq, n_eq


# ---------------------------------------------------------------- result object
class SimResult:
    """Probabilities and score distributions from one `simulate()` call. Read-only.

    Every probability is a plain float in [0, 1] keyed by the player name AS PASSED IN.
    Does NOT hold the raw sims (they are streamed and discarded), so anything not accumulated
    during the run cannot be recovered from this object — re-run with a new statistic instead.
    """

    TOP_KS = (5, 10, 20, 40)

    def __init__(self, names, n, seed, tau, cut_n, spread, baseline,
                 mu, sigma, acc, hist, cutline_hist, clipped=None):
        self.players = list(names)
        if len(set(self.players)) != len(self.players):
            raise ValueError("duplicate player names reached SimResult; every per-player dict "
                             "is keyed by name, so they would collapse silently")
        self.n = int(n)
        self.seed = seed
        self.tau = float(tau)
        self.cut_n = cut_n
        self.spread = float(spread)
        self.baseline = float(baseline)
        self.mean = {p: float(m) for p, m in zip(names, mu)}
        self.sigma = {p: float(s) for p, s in zip(names, sigma)}
        self._acc = acc
        self._hist = hist                    # (k, 4, B) counts, field-relative integer strokes
        self._clip = (np.zeros((len(self.players), _NROUNDS), dtype=np.int64)
                      if clipped is None else clipped)   # (k, 4) rounds outside hist support
        self._cutline = cutline_hist         # 1-d array of simulated cut lines (36-hole, rel)
        self.unrated = []                    # field names with no rating — DROPPED from the sim
        self.collisions = []                 # (name_a, name_b) folded together by normalisation
        self.duplicates = []                 # (kept, dropped, key) — one player entered twice

    # ---- core probabilities -------------------------------------------------
    def _p(self, key):
        return {p: float(v) for p, v in zip(self.players, self._acc[key] / self.n)}

    @property
    def win(self):
        """P(outright winner). A tie for the lead is split 1/k — i.e. a playoff is a coin flip.

        Does NOT model playoff skill (sudden-death is treated as equal-odds among the tied).
        """
        return self._p("win")

    @property
    def win_ties(self):
        """P(finishes tied-for-first or better), i.e. P(reaches the playoff). Always >= win."""
        return self._p("win_ties")

    @property
    def make_cut(self):
        """P(survives the 36-hole cut). Identically 1.0 for every player when cut_n is None."""
        return self._p("cut")

    def top(self, k, ties=False):
        """P(top-k). ties=False is DEAD-HEAT ('IMG' / exactly k slots); ties=True is 'INCL. TIES'.

        ties=True  -> P(shared position <= k). A six-way tie for 18th all count as top-20.
        ties=False -> expected number of the k slots the player holds, i.e. a tie straddling
                      the boundary contributes (k - n_better)/n_tied. This is the exact
                      dead-heat expectation and is a lower-variance estimator of the same
                      quantity than breaking ties at random.
        Does NOT model a book's actual dead-heat settlement arithmetic (stake reduction);
        it gives the probability, not the payout.
        """
        if k not in self.TOP_KS:
            raise ValueError(f"top-{k} was not accumulated; available: {self.TOP_KS} "
                             f"(k=1 is `win` / `win_ties`)")
        return self._p(("top%d_ties" % k) if ties else ("top%d" % k))

    def leader(self, rnd, ties=True):
        """P(leads after round `rnd` (1..4)). ties=True = shares the lead, False = outright alone.

        After the cut only cut-makers can lead, so rounds 3 and 4 are conditioned on survival
        (a missed-cut player gets 0). Round 4 with ties=True equals `win_ties`; with ties=False
        it is P(wins WITHOUT a playoff), which is strictly less than `win`.
        Does NOT handle mid-round leads — this is end-of-round only.
        """
        if rnd not in (1, 2, 3, 4):
            raise ValueError("rnd must be 1..4")
        return self._p("lead%d_ties" % rnd if ties else "lead%d" % rnd)

    # ---- distributions ------------------------------------------------------
    def _moments(self, counts, nclip, label, allow_clipped, pmf):
        """One histogram row -> {mean, sd, quantiles[, pmf], clipped}. Raises on silent clipping.

        The score histogram has a FIXED support of [_HIST_LO, _HIST_HI] and `simulate` clips
        into it, so a round outside that range is piled onto the edge bin. Reading a mean or an
        sd off that pile reports a number that is not the model's: 10 par players plus one at
        mean -40 gives a reported mean of -29.999 and an sd of 0.047. Probabilities are
        unaffected (they never touch the histogram), so this raises HERE rather than in
        `simulate` — and only for the distribution you actually asked for.
        """
        if nclip and not allow_clipped:
            raise ValueError(
                f"{label}: {nclip} of {int(counts.sum())} "
                f"simulated rounds fell outside the histogram support "
                f"[{_HIST_LO}, {_HIST_HI}] and were clipped onto the edge bin, so the mean and "
                f"sd below are NOT the model's. Fix the ratings (or widen _HIST_LO/_HIST_HI); "
                f"pass allow_clipped=True to read the clipped numbers anyway")
        vals = np.arange(_HIST_LO, _HIST_HI + 1, dtype=np.float64) + self.baseline
        c = counts.astype(np.float64)
        tot = c.sum()
        pr = c / tot if tot else c
        mean = float((vals * pr).sum())
        sd = float(math.sqrt(max(((vals - mean) ** 2 * pr).sum(), 0.0)))
        cdf = np.cumsum(pr)
        d = {f"p{int(t*100)}": float(vals[min(int(np.searchsorted(cdf, t)), len(vals) - 1)])
             for t in (0.10, 0.25, 0.50, 0.75, 0.90)}
        d.update(mean=mean, sd=sd, clipped=int(nclip),
                 clipped_frac=float(nclip / tot) if tot else 0.0)
        if pmf:
            d["pmf"] = {float(v): float(x) for v, x in zip(vals, pr) if x > 0}
        return d

    def round_dist(self, player, rnd=None, allow_clipped=False):
        """Per-round scoring distribution for one player: mean, sd, quantiles and the pmf.

        Returns {rnd: {"mean","sd","p10","p25","p50","p75","p90","pmf","clipped",
        "clipped_frac"}} with `rnd` 1..4, or a single dict if `rnd` is given. Scores are INTEGER
        strokes, field-relative, plus `baseline`; LOWER IS BETTER, so p10 is a GOOD round and
        p90 a bad one.
        These are UNCONDITIONAL round distributions — rounds 3 and 4 are the score the player
        WOULD shoot, not conditioned on making the cut. RAISES if any of that player's rounds
        were clipped to the histogram support (see `_moments`) — pass allow_clipped=True to
        read them anyway. Does NOT handle score-to-par (there is no par in pga_model.sqlite)
        or hole-by-hole detail.
        """
        if player not in self.mean:
            raise KeyError(f"{player!r} is not in this field ({len(self.players)} players)")
        if rnd is not None and rnd not in (1, 2, 3, 4):
            raise ValueError("rnd must be 1..4 or None")
        i = self.players.index(player)
        rounds = range(_NROUNDS) if rnd is None else [int(rnd) - 1]
        out = {r + 1: self._moments(self._hist[i, r], int(self._clip[i, r]),
                                    f"round_dist({player!r}, rnd={r + 1})",
                                    allow_clipped, pmf=True)
               for r in rounds}
        return out[rnd] if rnd else out

    def field_round_dist(self, allow_clipped=False):
        """Field-wide per-round score distribution (all players pooled), same shape as round_dist.

        Its sd is the ACROSS-PLAYER-AND-ROUND spread, which mixes player-skill spread, sigma
        and TAU. It is not sigma. RAISES on clipped rounds, like `round_dist`. Does NOT weight
        by who actually tees off (missed-cut players contribute rounds 3-4 they never played).
        """
        return {r + 1: self._moments(self._hist[:, r, :].sum(0), int(self._clip[:, r].sum()),
                                     f"field_round_dist() round {r + 1}",
                                     allow_clipped, pmf=False)
                for r in range(_NROUNDS)}

    def cut_line(self):
        """Simulated 36-hole cut line: mean and quantiles, field-relative + baseline*2.

        None whenever NO CUT WAS APPLIED — that is `cut_n is None`, and ALSO a field no bigger
        than the cut (k <= cut_n), where everyone plays on and `make_cut` is identically 1.0.
        Does NOT handle the tour's cut-line rounding conventions.
        """
        if self._cutline is None:
            return None
        v = self._cutline + 2.0 * self.baseline
        return {"mean": float(v.mean()), "sd": float(v.std()),
                "p10": float(np.quantile(v, 0.10)), "p50": float(np.quantile(v, 0.50)),
                "p90": float(np.quantile(v, 0.90))}

    # ---- convenience --------------------------------------------------------
    def as_dict(self):
        """Everything per player as {player: {...}} — JSON-safe, no numpy types.

        Does NOT include the per-round distributions (call round_dist for those).
        """
        w, wt, mc = self.win, self.win_ties, self.make_cut
        out = {}
        for p in self.players:
            d = {"mean": self.mean[p], "sigma": self.sigma[p],
                 "win": w[p], "win_ties": wt[p], "make_cut": mc[p]}
            for k in self.TOP_KS:
                d["top%d" % k] = self.top(k)[p]
                d["top%d_ties" % k] = self.top(k, ties=True)[p]
            for r in (1, 2, 3, 4):
                d["lead%d" % r] = self.leader(r, ties=True)[p]
            out[p] = d
        return out

    def table(self, k=10, sort="win"):
        """Formatted sanity table of the top `k` players by `sort`. Returns a string.

        Footers any dropped/unrated/duplicated/collided names, because a field-list problem
        that only lives on an attribute nobody prints is a field-list problem nobody sees.
        Purely a human-readable view; does NOT round-trip into anything.
        """
        w, wt, mc = self.win, self.win_ties, self.make_cut
        t5, t10, t20, t40 = (self.top(x) for x in (5, 10, 20, 40))
        t5t, t10t, t20t, t40t = (self.top(x, ties=True) for x in (5, 10, 20, 40))
        key = {"win": w, "top5": t5, "top10": t10, "top20": t20}.get(sort, w)
        order = sorted(self.players, key=lambda p: -key[p])[:k]
        L = max(len(p) for p in order) if order else 6
        head = (f"{'player'.ljust(L)}  {'mean':>6} {'sig':>5} | {'win%':>6} {'wint%':>6} | "
                f"{'t5':>5} {'t5T':>5} {'t10':>5} {'t10T':>5} {'t20':>5} {'t20T':>5} "
                f"{'t40':>5} {'t40T':>5} | {'cut%':>6}")
        lines = [head, "-" * len(head)]
        for p in order:
            lines.append(
                f"{p.ljust(L)}  {self.mean[p]:6.2f} {self.sigma[p]:5.2f} | "
                f"{100*w[p]:6.2f} {100*wt[p]:6.2f} | "
                f"{100*t5[p]:5.1f} {100*t5t[p]:5.1f} {100*t10[p]:5.1f} {100*t10t[p]:5.1f} "
                f"{100*t20[p]:5.1f} {100*t20t[p]:5.1f} {100*t40[p]:5.1f} {100*t40t[p]:5.1f} | "
                f"{100*mc[p]:6.2f}")
        if self.unrated:
            lines.append(f"!! {len(self.unrated)} UNRATED, dropped from the field: "
                         + ", ".join(map(str, self.unrated[:6]))
                         + (" ..." if len(self.unrated) > 6 else ""))
        for kept, dropped, _key in self.duplicates:
            lines.append(f"!! DUPLICATE entry dropped: {dropped!r} is the same player as "
                         f"{kept!r}")
        for a, b in self.collisions:
            lines.append(f"!! ratings names merged by normalisation: {a!r} + {b!r}")
        return "\n".join(lines)


# ---------------------------------------------------------------- the simulator
RHO = 0.09              # MEASURED 2026-08-13: corr(R1 resid, R2 resid) after removing the round
                        # field mean and the player's as-of rating. n=9,075 player-events,
                        # 95% CI [0.070, 0.111], placebo (players shuffled between rounds) +0.002.
                        # R1/R2 only — using all four rounds conditions on making the cut and
                        # drives rho NEGATIVE, which is the trap pga_ruler's constant note records.
                        # NOT the value a cut-line calibration wants (~0.60); that fit was
                        # absorbing other misspecification. pga_ruler ships 0.05 on its own fit.

def simulate(players, n=10000, seed=None, ratings=None, tau=None, rho=None, cut_n=CUT_N,
             cut_ties=True, spread=1.0, baseline=0.0, chunk=None):
    """Monte-Carlo a 72-hole stroke-play event. PURE: no network, no disk, no globals mutated.

    score[p, r] = mean[p] + sigma[p]*z[p, r] + tau*w[r], rounded to whole strokes; a
    top-`cut_n`-and-ties cut after round 2; ranks on the 72-hole total.

    players : mapping {name: (mean, sigma[, n_rounds])}, OR a sequence of names together with
              `ratings=` (any mapping accepted by `lookup`). Names not found are dropped and
              listed on `result.unrated`.
    n       : number of simulated tournaments.
    seed    : int, or None to draw a fresh OS seed (recorded on `result.seed`).
    tau     : shared per-round conditions sd in strokes; None uses module TAU. See the module
              header — tau is nearly unidentified from rank outcomes BY CONSTRUCTION.
    cut_n   : 65 (verified default), 50 for signature events / the Masters, 70 for the PGA
              Championship and The Open, None for a no-cut event (FedEx Cup playoffs).
    cut_ties: True = everyone level with the cut_n-th score survives (the real rule). False =
              a hard cut at exactly cut_n, with the tied bubble group broken AT RANDOM (an
              index-order tie-break was worth up to ~1pp of free make-cut to whoever happened
              to be listed early, since whole-stroke 36-hole ties are the norm).
    spread  : widen ratings away from the field mean, mirroring pga_ruler.SPREAD (1.30 there).
              Default 1.0 = the literal model.
    baseline: strokes added to every REPORTED score so distributions read as absolute strokes.
              Display only — it shifts no probability. Rounding happens BEFORE it is applied,
              so a fractional baseline yields fractional reported scores.

    DOES NOT HANDLE: course fit, weather, wind, wave/tee-time splits, player-week form
    correlation, withdrawals, in-play conditioning, playoff skill, alternates, or any market
    price. It is a rank engine over a frozen rating substrate and nothing more.
    """
    tau = float(TAU if tau is None else tau)
    _rho = float(RHO if rho is None else rho)
    if not (0.0 <= _rho < 1.0):
        raise ValueError('rho must be in [0,1), got %r' % (_rho,))
    chunk = int(CHUNK_SIMS if chunk is None else chunk)
    n = int(n)
    if n <= 0:
        raise ValueError("n must be positive")
    if chunk <= 0:
        raise ValueError("chunk must be positive")

    if isinstance(players, Mapping):
        names = list(players.keys())
        mu = np.array([float(v[0]) for v in players.values()], dtype=np.float64)
        sg = np.array([float(v[1]) for v in players.values()], dtype=np.float64)
        unrated, collisions, duplicates = [], [], []
        if spread != 1.0 and len(mu):
            fm = float(mu.mean())
            mu = fm + float(spread) * (mu - fm)
    elif isinstance(players, Sequence):
        if ratings is None:
            raise ValueError("a sequence of names needs ratings=")
        names, mu, sg, unrated, collisions, duplicates = field_ratings(
            players, ratings, spread=spread)
    else:
        raise TypeError("players must be a mapping or a sequence of names")

    k = len(names)
    if k < 2:
        raise ValueError(f"need at least 2 rated players, got {k}")
    if len(set(names)) != k:
        seen, dup = set(), set()
        for p in names:
            dup.add(p) if p in seen else seen.add(p)
        raise ValueError(
            f"the field contains the same name more than once: {sorted(dup)[:6]}. "
            f"Every result dict is keyed by name, so the duplicates would collapse and the "
            f"probabilities would stop summing to 1 — dedupe the field list first")
    _check_ratings(names, mu, sg, tau)
    if cut_n is not None:
        cut_n = int(cut_n)
        if cut_n < 1:
            raise ValueError("cut_n must be >= 1 or None")

    ss = np.random.SeedSequence(seed)
    used_seed = seed if seed is not None else int(ss.entropy if isinstance(ss.entropy, int)
                                                  else ss.entropy[0])
    n_chunks = (n + chunk - 1) // chunk
    children = ss.spawn(n_chunks)

    B = _HIST_HI - _HIST_LO + 1
    keys = (["win", "win_ties", "cut"]
            + [f"top{x}" for x in SimResult.TOP_KS]
            + [f"top{x}_ties" for x in SimResult.TOP_KS]
            + [f"lead{r}" for r in (1, 2, 3, 4)]
            + [f"lead{r}_ties" for r in (1, 2, 3, 4)])
    acc = {key: np.zeros(k, dtype=np.float64) for key in keys}
    hist = np.zeros(k * _NROUNDS * B, dtype=np.int64)
    clipped = np.zeros((k, _NROUNDS), dtype=np.int64)   # rounds pushed outside the hist support
    hbase = ((np.arange(k)[:, None] * _NROUNDS + np.arange(_NROUNDS)[None, :]) * B)[None, :, :]
    cut_lines = [] if cut_n is not None else None

    done = 0
    for ci in range(n_chunks):
        m = min(chunk, n - done)
        done += m
        rng = np.random.default_rng(children[ci])
        z = rng.standard_normal((m, k, _NROUNDS))
        w = rng.standard_normal((m, _NROUNDS)) * tau
        # PLAYER-WEEK FORM: one draw per player per sim, shared across his rounds. Weighted
        # sqrt(rho)/sqrt(1-rho) so per-round variance stays exactly sigma^2 — this re-attributes
        # variance into within-player correlation rather than adding any, so rho=0 is a no-op.
        if _rho > 0.0:
            wk = rng.standard_normal((m, k))
            z = (_rho ** 0.5) * wk[:, :, None] + ((1.0 - _rho) ** 0.5) * z
        sc = mu[None, :, None] + sg[None, :, None] * z + w[:, None, :]
        sc = np.rint(sc).astype(np.int32)                 # whole strokes -> real ties exist
        del z

        # per-round histogram (field-relative integer strokes). Out-of-support rounds are
        # clipped onto the edge bin — COUNTED, so the moment readers can refuse to report them.
        oob = (sc < _HIST_LO) | (sc > _HIST_HI)
        if oob.any():
            clipped += oob.sum(0)
        del oob
        b = np.clip(sc - _HIST_LO, 0, B - 1).astype(np.int64)
        hist += np.bincount((hbase + b).ravel(), minlength=k * _NROUNDS * B)
        del b

        cum = np.cumsum(sc, axis=2)                       # totals through each round
        tot2 = cum[:, :, 1]

        if cut_n is None:
            made = np.ones((m, k), dtype=bool)
        elif k <= cut_n:
            made = np.ones((m, k), dtype=bool)
        elif cut_ties:
            line = np.partition(tot2, cut_n - 1, axis=1)[:, cut_n - 1][:, None]
            made = tot2 <= line
            cut_lines.append(line[:, 0].astype(np.float64))
        else:
            # HARD cut at exactly cut_n. Scores are whole strokes, so the bubble is nearly
            # always a tie; break it with a uniform draw, never by position in the field list.
            # `tot2.argsort(1)` would hand the last survivor slot to whoever was listed first
            # (measured: 0.4922..0.5062 make-cut across 40 IDENTICAL players, a 12-sigma spread
            # that no choice of sort `kind` removes — ties need randomising, not sorting).
            u = rng.random((m, k))
            order = np.lexsort((u, tot2), axis=1)     # primary tot2, secondary uniform
            made = order.argsort(1) < cut_n
            cut_lines.append(np.take_along_axis(
                tot2, order[:, cut_n - 1][:, None], axis=1)[:, 0].astype(np.float64))
            del u, order
        acc["cut"] += made.sum(0)

        tot4 = cum[:, :, 3]

        # end-of-round leaders (r1, r2 over everyone; r3, r4 over cut-makers only)
        for r in range(_NROUNDS):
            alive = None if r < 2 else made
            n_lt, n_eq = _rank_counts(cum[:, :, r], alive)
            lead_t = (n_lt == 0)
            if alive is not None:
                lead_t &= alive
            acc[f"lead{r+1}_ties"] += lead_t.sum(0)
            acc[f"lead{r+1}"] += (lead_t & (n_eq == 1)).sum(0)
        del cum

        # final standings
        n_lt, n_eq = _rank_counts(tot4, made)
        pos_ties = n_lt + 1
        acc["win_ties"] += ((pos_ties == 1) & made).sum(0)
        acc["win"] += np.where((pos_ties == 1) & made, 1.0 / n_eq, 0.0).sum(0)
        for K in SimResult.TOP_KS:
            acc[f"top{K}_ties"] += ((pos_ties <= K) & made).sum(0)
            share = np.clip((K - n_lt) / np.maximum(n_eq, 1), 0.0, 1.0)
            acc[f"top{K}"] += np.where(made, share, 0.0).sum(0)
        del sc, tot2, tot4, made, n_lt, n_eq, pos_ties

    res = SimResult(names, n, used_seed, tau, cut_n, spread, baseline, mu, sg, acc,
                    hist.reshape(k, _NROUNDS, B),
                    np.concatenate(cut_lines) if cut_lines else None,
                    clipped=clipped)
    res.unrated = unrated
    res.collisions = collisions
    res.duplicates = duplicates
    return res


def tau_sensitivity(players, taus=(0.0, 1.0, 2.0), n=10000, seed=11, **kw):
    """Re-run the sim across `taus` on a COMMON seed and report how much each output moves.

    Exists because of module warning #1: a shared additive per-round factor cancels out of
    every rank statistic, so this is the empirical check on whether TAU is identifiable from
    win/top-N/cut at all. Returns {tau: {"win": {...}, "max_abs_win_delta": float, ...}}
    measured against the FIRST tau in the list.
    Does NOT tell you the right TAU — it tells you whether rank outcomes can ever tell you.
    """
    base = None
    out = {}
    for t in taus:
        r = simulate(players, n=n, seed=seed, tau=t, **kw)
        rec = {"win": r.win, "top10": r.top(10), "cut": r.make_cut,
               "field_round_sd": r.field_round_dist()[1]["sd"],
               "cut_line": (r.cut_line() or {}).get("mean")}
        if base is None:
            base = rec
            rec["max_abs_win_delta"] = 0.0
            rec["max_abs_top10_delta"] = 0.0
            rec["max_abs_cut_delta"] = 0.0
        else:
            rec["max_abs_win_delta"] = max(abs(rec["win"][p] - base["win"][p])
                                           for p in rec["win"])
            rec["max_abs_top10_delta"] = max(abs(rec["top10"][p] - base["top10"][p])
                                             for p in rec["top10"])
            rec["max_abs_cut_delta"] = max(abs(rec["cut"][p] - base["cut"][p])
                                           for p in rec["cut"])
        out[t] = rec
    return out
