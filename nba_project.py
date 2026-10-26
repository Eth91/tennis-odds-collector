#!/usr/bin/env python3
"""NBA player-stat projection engine (NBA_PROJECTION_PREREG.md). Research only: model estimates, never picks.

Outcome: Y = (min, pts, reb, ast, fg3m, stl, blk, tov) for a player who APPEARS (books void a DNP).
Cutoff: tip − 30 min; the only box scores used are from earlier dates.

Mean models, all from one walk-forward pass (walk): a date's predictions are computed from the state left by
earlier dates, then that date's games update the state — a future game cannot reach an earlier prediction.
  B1  season rate      this season's per-minute rate x this season's minutes (last season's when < 5 games)
  B2  recent form      per-minute rates over a 10-appearance half-life shrunk to a 60-appearance one; minutes
                       over a 5-appearance half-life shrunk to the 60
  M1  the engine       minutes: an EWMA (half-life h_m) shrunk to the long-run EWMA (k_m appearances).
                       rates: EWMA sums (half-life h_r) partially pooled toward the league's per-minute rate for
                       his position group (k_s minutes). context: what the opponent allowed to his group per
                       possession (this season blended with last, BLEND_K games) ^ a_opp; the game's expected
                       possessions ^ a_pace; home and back-to-back factors measured on 2022-23 (history only).
Distribution (M1): an analog ensemble. The K earlier player-games (any player, strictly earlier dates, 2 seasons)
whose own walk-forward M1 mean vectors (plus history depth and rest) are nearest; each one's realized outcome
vector is rescaled per stat to this mean, x' = (x + c) * (mu + c) / (mu_a + c) - c, and rounded stochastically.
One analog = one joint draw, so the covariance between stats and with minutes is the data's own, and a combo is
the sum of its components in the same draw.

Inputs NOT modeled in this version (shown as such): injuries and teammate absences (no point-in-time reports
before 2026-10-22, so no historical test), starting lineups, travel, referees, play types.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

import nba_proj_data as PD

VERSION = "proj-1.0"
STATS, COUNTS = PD.STATS, PD.COUNTS
NS = len(STATS)
C_SCALE = 0.25                     # the additive constant in the analog rescale (handles zero means / outcomes)
BLEND_K = 15                       # games: opponent factors blend this season with last (as nba_research)
COLD_MIN = 12.0                    # minutes for a player with no appearance at all (rare: debuts)

# the frozen configuration — chosen on 2023-24 only (nba_proj_eval.py --tune) and committed before any held-out
# period was scored. TUNED_ON records where it came from.
PROJ_CONFIG = {"h_m": 3, "k_m": 1.0, "h_r": 25, "k_pts": 50.0, "k_reb": 50.0, "k_ast": 50.0, "k_fg3m": 50.0,
               "k_stl": 400.0, "k_blk": 50.0, "k_tov": 50.0, "a_opp": 0.5, "a_pace": 0.5, "home": 1, "b2b": 0,
               "K": 400, "w_n": 1.0, "w_rest": 0.5}
TUNED_ON = "2023-24"     # nba_proj_eval.py --tune, 3 coordinate-descent passes, objective 0.37834 (normalized CRPS)
# frozen with the config: home / away / back-to-back multipliers measured on 2022-23, and the kNN feature scale
# (2022-23 standard deviations under PROJ_CONFIG) — so the VM and the backtest use the same numbers
PROJ_CONSTS = {"home": [0.9995, 1.01091, 1.01041, 1.01193, 1.0196, 1.00533, 1.01226, 0.99304],
               "away": [1.0005, 0.98909, 0.98959, 0.98807, 0.9804, 0.99467, 0.98774, 1.00696],
               "b2b": [1.06062, 1.00095, 0.9884, 0.97775, 1.02267, 0.95851, 0.94326, 0.97247]}
PROJ_SCALE = [0.49732, 0.58354, 0.4682, 0.49653, 0.39258, 0.19721, 0.23693, 0.33297, 0.97175, 0.27158]
PROJ_BLEND_W = 0.85            # the M1+mkt logit weight on FanDuel's no-vig, chosen on 2023-24 (log loss 0.68662)
GRID = {"h_m": [3, 6, 12], "k_m": [1.0, 3.0, 8.0], "h_r": [10, 25, 60],
        "k_pts": [50.0, 150.0, 400.0], "k_reb": [50.0, 150.0, 400.0], "k_ast": [50.0, 150.0, 400.0],
        "k_fg3m": [50.0, 150.0, 400.0], "k_stl": [50.0, 150.0, 400.0], "k_blk": [50.0, 150.0, 400.0],
        "k_tov": [50.0, 150.0, 400.0], "a_opp": [0.0, 0.5, 1.0], "a_pace": [0.0, 0.5, 1.0], "home": [0, 1],
        "b2b": [0, 1], "K": [100, 200, 400], "w_n": [0.5, 1.0, 2.0], "w_rest": [0.0, 0.5, 1.0]}
MEAN_KEYS = ("h_m", "k_m", "h_r", "k_pts", "k_reb", "k_ast", "k_fg3m", "k_stl", "k_blk", "k_tov", "a_opp",
             "a_pace", "home", "b2b")


def cfg_hash(cfg):
    return hashlib.sha1(json.dumps({k: cfg[k] for k in sorted(cfg)}, sort_keys=True).encode()).hexdigest()[:10]


# ── context constants measured on the history season only ──────────────────────────────────────────────────
def context_constants(rows, season="2022-23"):
    """Home and back-to-back multipliers per outcome, from `season` alone (per-minute rates for counts, minutes
    for min): (home / all, b2b / all). Fixed before any scored period."""
    last = {}
    acc = defaultdict(lambda: np.zeros(NS))
    for r in rows:
        if r["season"] != season:
            continue
        b2b = last.get(r["pid"]) is not None and _days(last[r["pid"]], r["date"]) == 1
        last[r["pid"]] = r["date"]
        v = np.array([r[s] for s in STATS], float)
        for key in ("all", "home" if r["home"] else "away", "b2b" if b2b else "rest"):
            acc[key] += v
            acc[key + "_n"] += 1
    def rate(key):
        v = acc[key] / max(1.0, acc[key + "_n"][0])
        return np.concatenate([[v[0]], v[1:] / max(v[0], 1e-9)])      # minutes per game, counts per minute
    allr = rate("all")
    home = rate("home") / allr
    b2b = rate("b2b") / allr
    return {"home": home.tolist(), "away": (rate("away") / allr).tolist(), "b2b": b2b.tolist()}


def _days(a, b):
    from datetime import date
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


# ── the walk-forward pass ───────────────────────────────────────────────────────────────────────────────────
class _Team:
    """Season-to-date defense (what each position group produced against the team) and possessions."""
    __slots__ = ("poss", "games", "allowed")

    def __init__(self):
        self.poss, self.games = 0.0, 0
        self.allowed = defaultdict(lambda: np.zeros(NS))


def walk(rows, cfg, targets=None, consts=None, keep=None):
    """Walk dates in order. Returns (out, out_targets): out[i] = {"b1", "b2", "m1": mean vectors (np, len 8),
    "n_hist", "rest"} for rows[i], each from the state left by EARLIER dates; out_targets[j] the same for
    targets[j] (the live slate: dicts with season, date, pid, team, opp, home, group), or None.
    `keep`: optional set of row indexes to keep outputs for (all by default)."""
    consts = consts or context_constants(rows)
    home_f = {1: np.array(consts["home"]), 0: np.array(consts["away"])}
    b2b_f = np.array(consts["b2b"])
    hs = sorted({cfg["h_m"], cfg["h_r"], 5, 10, 60})
    hi = {h: i for i, h in enumerate(hs)}                     # state rows: one per half-life
    decv = np.array([0.5 ** (1.0 / h) for h in hs])
    memo = {}                                                  # (season, team, group) -> opponent factors, per date
    ks = np.array([cfg["k_" + s] for s in COUNTS])
    P = {}                                                     # pid -> player state
    teams = defaultdict(_Team)                                 # (season, team) -> _Team
    league = defaultdict(lambda: {"poss": 0.0, "games": 0, "allowed": defaultdict(lambda: np.zeros(NS)),
                                  "rate": defaultdict(lambda: np.zeros(NS))})
    prev_final = {}                                            # season -> (teams, league) as the season ended

    def player(pid):
        p = P.get(pid)
        if p is None:
            p = P[pid] = {"W": np.zeros(len(hs)), "S": np.zeros((len(hs), NS)), "n": 0, "last": None, "season": {}}
        return p

    def group_prior(season, grp):
        """League per-minute rates for the group: this season to date plus last season's (both large samples)."""
        prv = prev_final.get(_prev(season), (None, None))[1]
        tot = league[season]["rate"][grp] + (prv["rate"][grp] if prv else 0)    # league-sized: no shrink needed
        if tot[0] <= 0:
            return np.array([COLD_MIN, 0.4, 0.18, 0.09, 0.04, 0.03, 0.02, 0.05])
        return np.concatenate([[COLD_MIN], tot[1:] / tot[0]])

    def opp_factor(season, opp, grp):
        k = (season, opp, grp)
        if k not in memo:
            memo[k] = _opp_factor(season, opp, grp)
        return memo[k]

    def _opp_factor(season, opp, grp):
        """(per-stat factor for what `opp` allows to `grp` per possession / the league, pace factor for opp)."""
        cur_t, cur_l = teams[(season, opp)], league[season]
        prv = prev_final.get(_prev(season))
        pt, pl = (prv[0].get(opp), prv[1]) if prv else (None, None)
        def per_poss(t, l):
            if t is None or l is None or t.poss <= 0 or l["poss"] <= 0:
                return None, None
            a = t.allowed[grp] / t.poss
            la = l["allowed"][grp] / l["poss"]
            f = np.where(la > 0, a / np.where(la > 0, la, 1), 1.0)
            pace = (t.poss / t.games) / (l["poss"] / l["games"])
            return f, pace
        fc, pc = per_poss(cur_t, cur_l)
        fp, pp = per_poss(pt, pl)
        n = cur_t.games
        if fc is None and fp is None:
            return np.ones(NS), 1.0
        if fc is None:
            return fp, pp
        if fp is None:
            return (n * fc + BLEND_K) / (n + BLEND_K), (n * pc + BLEND_K) / (n + BLEND_K)
        return (n * fc + BLEND_K * fp) / (n + BLEND_K), (n * pc + BLEND_K * pp) / (n + BLEND_K)

    def predict(t, parts=False):
        pid, season, grp = t["pid"], t["season"], t["group"] or "F"
        p = player(pid)
        prior = group_prior(season, grp)
        rest = _days(p["last"], t["date"]) if p["last"] else 30
        # B1: this season's rate x minutes; last season's sums added while he has < 5 games this season
        cs = p["season"].get(season)
        ps = p["season"].get(_prev(season))
        tot = (cs[1].copy() if cs else np.zeros(NS)) + (ps[1] if ps is not None and (not cs or cs[0] < 5) else 0)
        n_b1 = (cs[0] if cs else 0) + (ps[0] if ps is not None and (not cs or cs[0] < 5) else 0)
        if n_b1 and tot[0] > 0:
            b1 = np.concatenate([[tot[0] / n_b1], tot[1:] / tot[0] * (tot[0] / n_b1)])
        else:
            b1 = np.concatenate([[prior[0]], prior[1:] * prior[0]])
        # B2: recent form shrunk to long run, fixed constants
        W, S = p["W"], p["S"]
        W5, S5, W10, S10, W60, S60 = W[hi[5]], S[hi[5]], W[hi[10]], S[hi[10]], W[hi[60]], S[hi[60]]
        if W60 > 0 and S60[0] > 0:
            long_rate = S60[1:] / S60[0]
            m5 = S5[0] / W5
            m60 = S60[0] / W60
            b2_min = (W5 * m5 + 3.0 * m60) / (W5 + 3.0)
            b2_rate = (S10[1:] + 100.0 * long_rate) / (S10[0] + 100.0)
            b2 = np.concatenate([[b2_min], b2_rate * b2_min])
        else:
            b2 = np.concatenate([[prior[0]], prior[1:] * prior[0]])
        # M1
        Wm, Sm, Wr, Sr = W[hi[cfg["h_m"]]], S[hi[cfg["h_m"]]], W[hi[cfg["h_r"]]], S[hi[cfg["h_r"]]]
        if W60 > 0:
            m_short = Sm[0] / Wm
            m_long = S60[0] / W60
            m1_min = (Wm * m_short + cfg["k_m"] * m_long) / (Wm + cfg["k_m"])
        else:
            m1_min = prior[0]
        rate = (Sr[1:] + ks * prior[1:]) / (Sr[0] + ks)
        f_opp, pace = opp_factor(season, t["opp"], grp)
        own_pace = opp_factor(season, t["team"], grp)[1]
        ctx = np.ones(NS)
        f_o = np.power(np.clip(f_opp[1:], .3, 3.0), cfg["a_opp"])
        f_p = ((pace + own_pace) / 2.0) ** cfg["a_pace"]
        ctx[1:] *= f_o
        ctx[1:] *= f_p
        f_h = home_f[t["home"]] if cfg["home"] and t.get("home") in (0, 1) else np.ones(NS)
        ctx *= f_h
        b2b = bool(cfg["b2b"] and rest == 1)
        if b2b:
            ctx *= b2b_f
        m1 = np.concatenate([[m1_min * ctx[0]], rate * m1_min * ctx[1:]])
        o = {"b1": b1, "b2": b2, "m1": m1, "n_hist": p["n"], "rest": min(rest, 30)}
        if parts:              # the input breakdown the page shows: m1 = minutes x rate x opponent x pace x home (x b2b)
            o["parts"] = {"group": grp, "min": float(m1_min), "rate": rate.astype(float), "opp": f_o.astype(float),
                          "pace": float(f_p), "home": np.asarray(f_h, float), "b2b": b2b_f.astype(float) if b2b else None}
        return o

    def update(rs):
        by_game = defaultdict(list)
        for r in rs:
            by_game[(r["gid"], r["team"])].append(r)
        for r in rs:
            p = player(r["pid"])
            v = np.array([r[s] for s in STATS], float)
            p["W"] = p["W"] * decv + 1.0
            p["S"] = p["S"] * decv[:, None] + v
            p["n"] += 1
            p["last"] = r["date"]
            cs = p["season"].get(r["season"])
            if cs is None:
                cs = p["season"][r["season"]] = [0, np.zeros(NS)]
            cs[0] += 1
            cs[1] = cs[1] + v
            lg = league[r["season"]]
            lg["rate"][r["group"] or "F"] += v
        for (gid, team), grp_rows in by_game.items():
            season, opp = grp_rows[0]["season"], grp_rows[0]["opp"]
            poss = grp_rows[0]["team_poss"]
            # what `team`'s players produced is what `opp` allowed; possessions are the game's (team's own count)
            d = teams[(season, opp)]
            d.poss += poss
            d.games += 1
            lg = league[season]
            lg["poss"] += poss
            lg["games"] += 1
            for r in grp_rows:
                v = np.array([r[s] for s in STATS], float)
                d.allowed[r["group"] or "F"] += v
                lg["allowed"][r["group"] or "F"] += v

    out = [None] * len(rows)
    out_t = None if targets is None else [None] * len(targets)
    by_date = defaultdict(list)
    for i, r in enumerate(rows):
        by_date[r["date"]].append(i)
    t_by_date = defaultdict(list)
    if targets is not None:
        for j, t in enumerate(targets):
            t_by_date[t["date"]].append(j)
    dates = sorted(set(by_date) | set(t_by_date))
    season_seen = None
    for d in dates:
        s = PD.season_of(d)
        if season_seen and s != season_seen:
            prev_final[season_seen] = ({k[1]: v for k, v in teams.items() if k[0] == season_seen}, league[season_seen])
        season_seen = s
        memo.clear()                                           # state changes only between dates
        for i in by_date.get(d, []):
            if keep is None or i in keep:
                out[i] = predict(rows[i])
        for j in t_by_date.get(d, []):
            out_t[j] = predict(targets[j], parts=True)
        update([rows[i] for i in by_date.get(d, [])])
    return out, out_t


def _prev(season):
    y = int(season[:4]) - 1
    return f"{y}-{str(y + 1)[2:]}"


# ── the analog ensemble ─────────────────────────────────────────────────────────────────────────────────────
def features(mu, n_hist, rest, cfg):
    """kNN space: log1p of the 8 means, history depth and rest (weighted)."""
    mu = np.asarray(mu, float)
    f = np.log1p(np.clip(mu, 0, None))
    extra = np.stack([cfg["w_n"] * np.log1p(np.asarray(n_hist, float)),
                      cfg["w_rest"] * np.log1p(np.minimum(np.asarray(rest, float), 30))], axis=-1)
    return np.concatenate([f, extra], axis=-1)


def neighbors(tf, pf, K, scale):
    """Indexes of the K nearest pool rows (Euclidean on standardized features) for each target row."""
    tf, pf = tf / scale, pf / scale
    K = min(K, len(pf))
    out = np.empty((len(tf), K), dtype=np.int64)
    pn = (pf * pf).sum(1)
    for a in range(0, len(tf), 512):
        b = tf[a:a + 512]
        d = (b * b).sum(1)[:, None] + pn[None, :] - 2.0 * b @ pf.T
        out[a:a + 512] = np.argpartition(d, K - 1, axis=1)[:, :K]
    return out


class Dist:
    """The joint predictive distribution for a block of targets: K analog draws each, rescaled per stat.
    vals[t, k, s] is the continuous rescaled value; integers come from stochastic rounding, done exactly
    (probabilities), never by sampling."""

    def __init__(self, mu_t, pool_mu, pool_y, nb):
        mu_t = np.asarray(mu_t, float)
        ma = pool_mu[nb]                                       # (T, K, 8)
        ya = pool_y[nb]
        r = (mu_t[:, None, :] + C_SCALE) / (ma + C_SCALE)
        self.vals = np.clip((ya + C_SCALE) * r - C_SCALE, 0, None)
        self.mu = mu_t

    def market_vals(self, market):
        idx = [STATS.index(s) for s in PD.MARKET_PARTS[market]]
        return self.vals[:, :, idx].sum(-1)

    @staticmethod
    def p_ge(v, m):
        """P(stochastically rounded v >= integer m), elementwise."""
        fl = np.floor(v)
        return np.where(fl >= m, 1.0, np.where(fl == m - 1, v - fl, 0.0))

    def probs(self, market, lines):
        """(p_over, p_under, p_push) arrays for one line per target (half or whole)."""
        v = self.market_vals(market)
        L = np.asarray(lines, float)
        k = np.floor(L)[:, None]
        half = (L - np.floor(L)) > 0.25                       # a half-point line cannot push
        over = self.p_ge(v, k + 1).mean(1)                     # X >= k+1
        push = np.where(half, 0.0, self.p_ge(v, k).mean(1) - over)
        return over, 1.0 - over - push, push

    def pmf(self, market, grid):
        """(T, G) probability of each integer 0..G-1 (the last bin collects the tail)."""
        v = self.market_vals(market)
        fl = np.floor(v)
        f = v - fl
        T, K = v.shape
        out = np.zeros((T, grid))
        lo = np.clip(fl, 0, grid - 1).astype(int)
        hi = np.clip(fl + 1, 0, grid - 1).astype(int)
        rows = np.repeat(np.arange(T), K)
        np.add.at(out, (rows, lo.ravel()), ((1 - f) / K).ravel())
        np.add.at(out, (rows, hi.ravel()), (f / K).ravel())
        return out

    def quantiles(self, market, qs=(0.1, 0.5, 0.9)):
        pm = self.pmf(market, 160)
        cdf = np.cumsum(pm, 1)
        return np.stack([(cdf >= q).argmax(1) for q in qs], 1)

    def mean(self, market):
        return self.market_vals(market).mean(1)


def crps_pmf(pmf, y):
    """CRPS of a discrete distribution on 0..G-1 against integer outcomes y (array)."""
    cdf = np.cumsum(pmf, 1)
    grid = np.arange(pmf.shape[1])[None, :]
    step = (grid >= np.asarray(y)[:, None]).astype(float)
    return ((cdf - step) ** 2).sum(1)


def logscore_pmf(pmf, y, K):
    """-log P(Y = y) with add-0.5 smoothing over the grid (the prereg's rule)."""
    G = pmf.shape[1]
    y = np.clip(np.asarray(y, int), 0, G - 1)
    p = (pmf[np.arange(len(y)), y] * K + 0.5 / G) / (K + 0.5)
    return -np.log(p)


def nb_pmf(mu, disp, grid):
    """Negative binomial pmf on 0..grid-1 (last bin = tail) for B2's naive marginals; disp = size r (np.inf =
    Poisson). Computed with lgamma, no scipy."""
    mu = np.maximum(np.asarray(mu, float), 1e-6)
    k = np.arange(grid)[None, :]
    if not np.isfinite(disp):
        lp = k * np.log(mu[:, None]) - mu[:, None] - np.vectorize(math.lgamma)(k + 1.0)
    else:
        r = disp
        lg = np.vectorize(math.lgamma)
        lp = (lg(k + r) - lg(r) - lg(k + 1.0) + r * np.log(r / (r + mu[:, None])) + k * np.log(mu[:, None] / (r + mu[:, None])))
    p = np.exp(lp)
    p[:, -1] += np.clip(1 - p.sum(1), 0, None)
    return p


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def blend(p_model, p_mkt, w):
    return 1 / (1 + np.exp(-((1 - w) * logit(p_model) + w * logit(p_mkt))))


def no_vig(o, u):
    a, b = 1 / np.asarray(o, float), 1 / np.asarray(u, float)
    return a / (a + b)


# ── live: the slate ─────────────────────────────────────────────────────────────────────────────────────────
GAMELOGS = PD.HERE / "nba_gamelogs.sqlite"
MATCHUP = PD.HERE / "nba_matchup.sqlite"
PROFILES = PD.HERE / "nba_profiles.sqlite"
CACHE = PD.HERE / "nba_proj_cache.pkl"
CUTOFF_MIN = 30
POOL_DAYS = 730
MARKETS_LIVE = ("points", "rebounds", "assists", "threes", "pra", "pts_reb", "pts_ast", "reb_ast", "steals", "blocks",
                "turnovers")


def project(rows, slate, cfg=None, consts=None, scale=None):
    """Projections for slate targets (season, date, pid, team, opp, home, group): (Dist, target outputs, pool
    stats). The analog pool is every player-game within POOL_DAYS before the slate's first date."""
    from datetime import date, timedelta
    cfg = cfg or PROJ_CONFIG
    consts = consts or PROJ_CONSTS or context_constants(rows)
    out, ot = walk(rows, cfg, targets=slate, consts=consts)
    first = min(t["date"] for t in slate)
    lo = (date.fromisoformat(first) - timedelta(days=POOL_DAYS)).isoformat()
    pool = [i for i, r in enumerate(rows) if lo <= r["date"] < first and out[i] is not None]
    pmu = np.array([out[i]["m1"] for i in pool])
    py = np.array([[rows[i][s] for s in STATS] for i in pool], float)
    py[:, 0] = np.round(py[:, 0])
    pf = features(pmu, [out[i]["n_hist"] for i in pool], [out[i]["rest"] for i in pool], cfg)
    tmu = np.array([o["m1"] for o in ot])
    tf = features(tmu, [o["n_hist"] for o in ot], [o["rest"] for o in ot], cfg)
    sc = np.asarray(scale if scale is not None else (PROJ_SCALE or pf.std(0)), float)
    sc = np.where(sc > 0, sc, 1.0)
    nb = neighbors(tf, pf, cfg["K"], sc)
    return Dist(tmu, pmu, py, nb), ot, {"pool": len(pool), "through": max((rows[i]["date"] for i in pool), default=None),
                                        "pool_mean": [round(float(x), 2) for x in pmu.mean(0)] if len(pmu) else None}


def compact_pmf(pm, eps=5e-5):
    """[start, [p...]] — the pmf over integers with negligible tails trimmed, 4 decimals."""
    nz = np.where(pm > eps)[0]
    if not len(nz):
        return [0, [1.0]]
    a, b = int(nz[0]), int(nz[-1])
    return [a, [round(float(x), 4) for x in pm[a:b + 1]]]


def summarize(d, j, market, grid=160):
    sub = Dist.__new__(Dist)
    sub.vals, sub.mu = d.vals[j:j + 1], d.mu[j:j + 1]
    pm = sub.pmf(market, grid)[0]
    cdf = np.cumsum(pm)
    q = lambda x: int((cdf >= x).argmax())
    return {"mean": round(float(sub.mean(market)[0]), 2), "q10": q(.1), "q50": q(.5), "q90": q(.9),
            "pmf": compact_pmf(pm)}


def availability_table(news_db, matchup_db, lines_db=None, cutoff_min=CUTOFF_MIN):
    """{status: [appeared, n]} — the official report's status at T−cutoff (the latest snapshot published before
    it; the tip from nba_lines) against whether the player appeared (min > 0). 2026-27 only (reports exist from
    2026-10-22). Shown with its n."""
    import datetime as dt_
    n, m, q = PD._ro(news_db), PD._ro(matchup_db), PD._ro(lines_db or PD.HERE / "nba_lines.sqlite")
    out = defaultdict(lambda: [0, 0])
    if n is None or m is None or q is None:
        return {}
    season_gids = [g for (g,) in m.execute("SELECT gid FROM games WHERE home_pts IS NOT NULL AND season='2026-27'")]
    cut = {}
    if not season_gids:
        return {}
    for g, t in q.execute(f"SELECT gid, MIN(tip_utc) FROM quotes WHERE gid IN ({','.join('?' * len(season_gids))}) "
                          f"GROUP BY gid", season_gids):
        if t:
            tt = dt_.datetime.fromisoformat(t.replace("Z", "+00:00")) - dt_.timedelta(minutes=cutoff_min)
            cut[g] = tt.isoformat()
    played = {(g, p) for g, p, mn in m.execute("SELECT gid, pid, min FROM player_games") if mn and mn > 0}
    games = {}
    for gid, d, h, a in m.execute("SELECT gid, date, home, away FROM games WHERE home_pts IS NOT NULL AND season='2026-27'"):
        games[(d, h)] = games[(d, a)] = gid
    tips = {}
    for d, team, pid, status, pub in n.execute("SELECT game_date, team, pid, status, published_at FROM snapshots "
                                                "WHERE pid IS NOT NULL ORDER BY published_at"):
        gid = games.get((d, team))
        if gid and gid in cut and pub < cut[gid]:
            tips[(gid, pid)] = (status, pub)                 # the last listing published before the cutoff
    for (gid, pid), (status, pub) in tips.items():
        o = out[status]
        o[1] += 1
        o[0] += (gid, pid) in played
    return {k: list(v) for k, v in out.items()}


def log_forecasts(db, items, now):
    """Prospective record (prereg test C): one 'first' row per (gid, pid, market, version) the first time it is
    projected, and a 'cutoff' row rewritten on every build until T−CUTOFF_MIN — so after the cutoff it holds the
    last forecast made before it. items: dicts with gid, pid, market, tip, line, book, over, under, p_over, p_push,
    p_blend, mean."""
    import datetime as dt_
    import sqlite3 as sq
    con = sq.connect(db, timeout=30)
    con.execute("CREATE TABLE IF NOT EXISTS forecasts (kind TEXT, logged_at TEXT, gid TEXT, pid INTEGER, market TEXT, "
                "tip TEXT, line REAL, book TEXT, over REAL, under REAL, p_over REAL, p_push REAL, p_blend REAL, "
                "mean REAL, version TEXT, PRIMARY KEY (kind, gid, pid, market, version))")
    stamp = now.astimezone(dt_.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    n = 0
    for it in items:
        tip = dt_.datetime.fromisoformat(str(it["tip"]).replace("Z", "+00:00"))
        if now >= tip - dt_.timedelta(minutes=CUTOFF_MIN):
            continue                                          # past the cutoff: the record is closed
        vals = (stamp, it["gid"], it["pid"], it["market"], str(it["tip"]), it["line"], it["book"], it["over"],
                it["under"], it["p_over"], it["p_push"], it["p_blend"], it["mean"], VERSION)
        con.execute("INSERT OR IGNORE INTO forecasts VALUES ('first',?,?,?,?,?,?,?,?,?,?,?,?,?,?)", vals)
        con.execute("INSERT OR REPLACE INTO forecasts VALUES ('cutoff',?,?,?,?,?,?,?,?,?,?,?,?,?,?)", vals)
        n += 1
    con.commit()
    con.close()
    return n


INPUTS_USED = ["box scores before the game date (this season and the previous three)", "minutes and per-minute rates",
               "league rates for his position group", "opponent's allowed rates for his group (blended with last season)",
               "both teams' pace", "home/away", "back-to-back"]
INPUTS_MISSING = ["injury news and teammate absences (no point-in-time history to test them before 2026-10-22)",
                  "starting lineups", "travel", "referees", "play types"]


def _cache_key(gamelogs, matchup):
    import os
    return (VERSION, cfg_hash(PROJ_CONFIG), os.path.getmtime(gamelogs) if os.path.exists(gamelogs) else 0,
            os.path.getmtime(matchup) if os.path.exists(matchup) else 0)


def load_cache(cache=None):
    import pickle
    try:
        return pickle.loads(Path(cache or CACHE).read_bytes())
    except (OSError, EOFError, pickle.UnpicklingError, AttributeError, ValueError):
        return None


def refresh(targets, gamelogs=None, matchup=None, profiles=None, cache=None, force=False, news=None, lines_db=None):
    """Project `targets` (dicts: gid, date, pid, team, opp, home) and write the cache the 2-minute build reads.
    Skipped when the cache already holds every target and the box-score stores have not changed. The heavy part
    (load + walk, ~1 min on the VM) runs here, never inside the page build. Returns a short status string."""
    import os
    import pickle
    gamelogs, matchup, profiles, cache = gamelogs or GAMELOGS, matchup or MATCHUP, profiles or PROFILES, cache or CACHE
    key = _cache_key(gamelogs, matchup)
    want = {(t["gid"], t["pid"]): t for t in targets}
    old = load_cache(cache)
    if not force and old and old.get("key") == key and set(want) <= set(old.get("at", {})):
        return f"cache current ({len(old['at'])} players)"
    rows, _, pos = PD.load_box(gamelogs, matchup, profiles)
    if not rows:
        return "no box scores"
    grp = {r["pid"]: r["group"] for r in rows}
    last = defaultdict(list)
    for r in rows:
        last[r["pid"]].append(r)
    keys = sorted(want)
    slate, no_group = [], 0
    for k in keys:
        t = want[k]
        g = grp.get(t["pid"]) or PD.group_of(pos.get(t["pid"]))
        no_group += g is None
        slate.append(dict(t, season=PD.season_of(t["date"]), group=g or "F"))   # unknown: forwards' rates (counted)
    d, ot, ps = project(rows, slate)
    l10 = np.array([np.mean([[r[s] for s in STATS] for r in last[t["pid"]][-10:]], 0) if len(last[t["pid"]]) >= 10
                    else np.full(NS, np.nan) for t in slate])
    obj = {"key": key, "at": {k: j for j, k in enumerate(keys)}, "vals": d.vals.astype(np.float32), "mu": d.mu,
           "n_hist": [o["n_hist"] for o in ot], "rest": [o["rest"] for o in ot], "through": max(r["date"] for r in rows),
           "parts": [o["parts"] for o in ot],
           "pool": ps["pool"], "no_group": no_group, "last10": l10, "made_at": __import__("datetime").datetime.now(
               __import__("datetime").timezone.utc).isoformat(timespec="seconds"),
           "availability": availability_table(news, matchup, lines_db) if news is not None else None}
    tmp = Path(str(cache) + ".tmp")
    tmp.write_bytes(pickle.dumps(obj))
    os.replace(tmp, cache)
    return f"projected {len(keys)} players, box scores through {obj['through']}"


def for_payload(props, games, now, log_db=None, cache=None, gamelogs=None, matchup=None):
    """(proj by prop id, players {pid: {stat: summary}}, meta) from the refresh job's cache. Never a stand-in
    number: a prop the cache does not hold carries no projection, and meta says why and how many."""
    import datetime as dt_
    gamelogs, matchup = gamelogs or GAMELOGS, matchup or MATCHUP
    meta = {"version": VERSION, "config": cfg_hash(PROJ_CONFIG), "tuned_on": TUNED_ON, "blend_w": PROJ_BLEND_W,
            "cutoff": f"tip − {CUTOFF_MIN} min; box scores from earlier dates only",
            "generated_at": now.astimezone(dt_.timezone.utc).isoformat(timespec="seconds"),
            "inputs_used": INPUTS_USED, "inputs_missing": INPUTS_MISSING, "target": "conditional on playing (books void a DNP)",
            "error": None, "stale": False, "backtest": backtest_summary()}
    if TUNED_ON is None:
        meta["error"] = "the model config is not frozen yet"
        return {}, {}, meta
    try:
        hit = load_cache(cache)
        if hit is None:
            meta["error"] = "projections not computed yet (nba_project.py --refresh)"
            return {}, {}, meta
        gmap = {g["gid"]: g for g in games}
        d = Dist.__new__(Dist)
        d.vals, d.mu = hit["vals"].astype(float), np.asarray(hit["mu"], float)
        at = hit["at"]
        meta.update(logs_through=hit["through"], pool=hit["pool"], projected_at=hit.get("made_at"))
        if hit.get("key") != _cache_key(gamelogs, matchup):
            meta["refresh_pending"] = True                    # new box scores since; the refresh job is behind
        dates = [gmap[p["gid"]].get("date_et") or gmap[p["gid"]].get("date") for p in props if p["gid"] in gmap]
        if dates:
            gap = (dt_.date.fromisoformat(min(dates)) - dt_.date.fromisoformat(hit["through"])).days
            if gap > 3:
                meta["stale"] = True
                meta["stale_reason"] = f"latest box score is {hit['through']}, {gap} days before the slate"
        by_prop, players, rows_used = {}, {}, set()
        for p in props:
            j = at.get((p["gid"], p["pid"]))
            if j is None:
                continue
            rows_used.add(j)
            s = summarize(d, j, p["market"])
            s["n_hist"], s["rest"] = int(hit["n_hist"][j]), int(hit["rest"][j])
            by_prop[p["id"]] = s
            if str(p["pid"]) not in players:
                players[str(p["pid"])] = {m: {k: v for k, v in summarize(d, j, m).items() if k != "pmf"}
                                          for m in ("points", "rebounds", "assists", "threes", "steals", "blocks", "turnovers")}
                players[str(p["pid"])]["min"] = {k: v for k, v in summarize(d, j, "min", 70).items() if k != "pmf"}
                players[str(p["pid"])]["inputs"] = inputs_of(hit, j)
        meta["coverage"] = {"props": len(props), "projected": len(by_prop),
                            "thin_history": sum(1 for v in by_prop.values() if v["n_hist"] < 10),
                            "players": len(players), "unknown_position": hit.get("no_group", 0)}
        # drift: tonight's projected means against the same players' last-10 averages (near 0 when inputs are sane)
        if rows_used and hit.get("last10") is not None:
            ix = sorted(rows_used)
            diff = np.asarray(hit["mu"], float)[ix] - np.asarray(hit["last10"], float)[ix]
            meta["drift"] = {s: (round(float(np.nanmedian(diff[:, k])), 2) if np.isfinite(diff[:, k]).any() else None)
                             for k, s in enumerate(STATS)}
        meta["availability"] = hit.get("availability")      # from the refresh job (finished games only)
        if log_db is not None:
            items = []
            for p in props:
                s, j = by_prop.get(p["id"]), at.get((p["gid"], p["pid"]))
                bk = next((b for b in ("fd", "dk") if (p["books"].get(b) or {}).get("main") is not None), None)
                if s is None or bk is None or p["gid"] not in gmap:
                    continue
                line = p["books"][bk]["main"]
                r = next(r for r in p["books"][bk]["rungs"] if r[0] == line)
                sub = Dist.__new__(Dist)
                sub.vals, sub.mu = d.vals[j:j + 1], d.mu[j:j + 1]
                po, pu, pp = sub.probs(p["market"], [line])
                pc = float(po[0] / max(po[0] + pu[0], 1e-9))
                items.append({"gid": p["gid"], "pid": p["pid"], "market": p["market"], "tip": gmap[p["gid"]].get("utc"),
                              "line": line, "book": bk, "over": r[1], "under": r[2], "p_over": pc, "p_push": float(pp[0]),
                              "p_blend": float(blend(np.array([pc]), np.array([no_vig(r[1], r[2])]), PROJ_BLEND_W)[0]),
                              "mean": s["mean"]})
            meta["logged"] = log_forecasts(log_db, items, now)
        return by_prop, players, meta
    except Exception as e:                                                   # noqa: BLE001
        meta["error"] = f"projection failed ({type(e).__name__}: {str(e)[:120]})"
        return {}, {}, meta


def inputs_of(hit, j):
    """The projection's input breakdown for the page: per stat [minutes, per-minute rate, opponent, pace, home,
    back-to-back] whose product is μ (the mean the distribution is built around); None for an older cache."""
    parts = hit.get("parts")
    if not parts or parts[j] is None:
        return None
    q = parts[j]
    b2b = q["b2b"] if q["b2b"] is not None else np.ones(NS)
    r4 = lambda x: round(float(x), 4)
    out = {"group": q["group"], "min": r4(q["min"]), "mu": {}}
    for k, st in enumerate(STATS):
        if k == 0:
            out["min_f"] = {"home": r4(q["home"][0]), "b2b": r4(b2b[0])}
        else:
            out[st] = [r4(q["rate"][k - 1]), r4(q["opp"][k - 1]), r4(q["pace"]), r4(q["home"][k]), r4(b2b[k])]
        out["mu"][st] = round(float(hit["mu"][j][k]), 2)
    return out


RESULTS = PD.HERE / "PROJECTION_RESULTS.json"


def backtest_summary(path=None):
    """The headline numbers of the pre-registered evaluation (PROJECTION_RESULTS.json, or its copy in
    nba_proj_results.py — the VM deploy copies code only), for the page."""
    try:
        r = json.loads(Path(path or RESULTS).read_text())
    except (OSError, ValueError):
        try:
            import nba_proj_results
            r = nba_proj_results.RESULTS
        except ImportError:
            return None
    out = {"version": r.get("version"), "generated_at": r.get("generated_at"), "periods": {}}
    for season, p in (r.get("periods") or {}).items():
        if not p:
            continue
        row = {"n": p.get("n"), "dates": p.get("dates"), "crps_vs_b2": p.get("norm_crps_m1_minus_b2"), "label": p.get("label"),
               "cover80": {s: round(v.get("cover80", 0), 3) for s, v in (p.get("stats") or {}).items()}}
        mk = p.get("market")
        if mk:
            row["market"] = {"n": mk["n"], "model_ll": mk["m1"]["logloss"], "blend_ll": mk["m1+mkt"]["logloss"],
                             "close_ll": mk["market"]["logloss"], "model_minus_close": mk["m1_minus_market_ll"],
                             "blend_minus_close": mk["blend_minus_market_ll"], "sim": mk.get("sim")}
        out["periods"][season] = row
    out["verdicts"] = r.get("verdicts")
    return out


def slate_targets(now=None, rows=None, lines_db=None, index=None, days=120):
    """Today's and tomorrow's (ET) games: every player who appeared for one of those teams in the last `days` days
    (his latest team), plus every player on the book board for those games (team from the player index)."""
    import datetime as dt_
    import nba_rosters as RO
    now = now or dt_.datetime.now(dt_.timezone.utc)
    et = now.astimezone(__import__("zoneinfo").ZoneInfo("America/New_York")).date()
    dates = {et.isoformat(), (et + dt_.timedelta(days=1)).isoformat()}
    games = [g for g in RO.schedule() if g["date_et"] in dates]
    side = {}
    for g in games:
        side[(g["gid"], g["home"])] = (g["away"], 1, g["date_et"])
        side[(g["gid"], g["away"])] = (g["home"], 0, g["date_et"])
    if rows is None:
        rows, _, _ = PD.load_box(GAMELOGS, MATCHUP, PROFILES)
    lo = (et - dt_.timedelta(days=days)).isoformat()
    latest = {}
    for r in rows:
        if r["date"] >= lo:
            latest[r["pid"]] = r["team"]
    out = {}
    for g in games:
        for team in (g["home"], g["away"]):
            opp, home, date = side[(g["gid"], team)]
            for pid, t in latest.items():
                if t == team:
                    out[(g["gid"], pid)] = {"gid": g["gid"], "date": date, "pid": pid, "team": team, "opp": opp, "home": home}
    q = PD._ro(lines_db or PD.HERE / "nba_lines.sqlite")
    try:
        idx = {int(k): v[0] for k, v in json.loads(Path(index or PD.HERE / "nba_player_index.json").read_text())["players"].items()}
    except (OSError, ValueError, KeyError):
        idx = {}
    if q is not None and games:
        gids = [g["gid"] for g in games]
        for gid, pid in q.execute(f"SELECT DISTINCT gid, pid FROM board WHERE pid IS NOT NULL AND gid IN ({','.join('?' * len(gids))})", gids):
            team = latest.get(pid) or idx.get(pid)
            if (gid, team) in side and (gid, pid) not in out:
                opp, home, date = side[(gid, team)]
                out[(gid, pid)] = {"gid": gid, "date": date, "pid": pid, "team": team, "opp": opp, "home": home}
    return list(out.values()), rows


def board_targets(now=None, lines_db=None):
    """{(gid, pid)} on the book board for today's and tomorrow's (ET) games — the refresh job's cheap check."""
    import datetime as dt_
    import nba_rosters as RO
    now = now or dt_.datetime.now(dt_.timezone.utc)
    et = now.astimezone(__import__("zoneinfo").ZoneInfo("America/New_York")).date()
    dates = {et.isoformat(), (et + dt_.timedelta(days=1)).isoformat()}
    gids = [g["gid"] for g in RO.schedule() if g["date_et"] in dates]
    q = PD._ro(lines_db or PD.HERE / "nba_lines.sqlite")
    if q is None or not gids:
        return set()
    return {(g, p) for g, p in q.execute(f"SELECT DISTINCT gid, pid FROM board WHERE pid IS NOT NULL AND gid IN "
                                         f"({','.join('?' * len(gids))})", gids)}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="NBA projection engine (research only)")
    ap.add_argument("--refresh", action="store_true", help="cron: project today's and tomorrow's players into the cache")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.refresh:
        before = load_cache()
        current = before is not None and before.get("key") == _cache_key(GAMELOGS, MATCHUP)
        if current and not a.force:
            board = board_targets()
            missing = [k for k in board if k not in before["at"]]
            if not missing:
                print(f"nba_project --refresh: cache current ({len(before['at'])} players, {len(board)} on the board)")
                return
        targets, rows = slate_targets()
        print("nba_project --refresh:", refresh(targets, force=True, news=PD.HERE / "nba_news.sqlite"))


if __name__ == "__main__":
    main()

