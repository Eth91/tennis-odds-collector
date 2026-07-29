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
import sqlite3
import statistics as st
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "pga_model.sqlite"
LINES = HERE / "golf_lines.sqlite"
UA = {"User-Agent": "Mozilla/5.0"}

HALF_LIFE_D = 120.0     # recency half-life for the rating (form vs ability balance)
K_SHRINK = 12.0         # pseudo-rounds of field-average shrinkage
RHO = 0.25              # share of round variance that is player-week form (round dependence)
SIG_SHRINK = 20.0       # rounds of shrinkage of player sd toward the global sd
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


def fit(asof=None):
    """{player: (rating, sigma, n_rounds)} using ONLY rounds strictly before `asof`."""
    asof = asof or "9999"
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT event_id, date, player, rnd, score FROM rounds "
                       "WHERE date < ? ORDER BY date", (asof,)).fetchall()
    con.close()
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
        prov[nm] = st.mean(v) * len(v) / (len(v) + K_SHRINK)
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
        w = 0.5 ** (max(age, 0) / HALF_LIFE_D)
        per[nm].append((sc - fm, w))
    g_sd = st.pstdev([d for v in per.values() for d, _ in v]) or 2.8
    out = {}
    for nm, v in per.items():
        sw = sum(w for _, w in v)
        mu = sum(d * w for d, w in v) / sw if sw else 0.0
        rating = mu * sw / (sw + K_SHRINK)               # shrink to field average
        n = len(v)
        sd = st.pstdev([d for d, _ in v]) if n >= 5 else g_sd
        sigma = (sd * n + g_sd * SIG_SHRINK) / (n + SIG_SHRINK)
        if n < MIN_ROUNDS:
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
    ma = ma + cf.get(a, cf.get(norm(a), 0.0))
    mb = mb + cf.get(b, cf.get(norm(b), 0.0))
    mu = (mb - ma) * rounds
    var = rounds * (sa * sa + sb * sb) + RHO * (sa * sa + sb * sb) * (rounds - 1)
    return _phi(mu / math.sqrt(max(var, 1e-6)))


def simulate(R, field, n_sims=8000, seed=7, course_fit=None, wave=None,
             wave_shift=0.0):
    """Win/top5/10/20/make-cut probs via MC: 4 rounds, player-week effect, top-70 cut."""
    import numpy as np
    rng = np.random.default_rng(seed)
    names = [p for p in field if (norm(p) in R or p in R)]
    # COURSE FIT (blindness #3): per-player strokes/round adjustment at THIS venue,
    # already shrunk by pga_context (course history is the most over-claimed golf edge).
    cf = course_fit or {}
    mus = np.array([(R.get(norm(p)) or R[p])[0] + cf.get(p, cf.get(norm(p), 0.0))
                    for p in names])
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
    tot2 = 2 * (mus + wk) + eps[:, :, :2].sum(2)          # 36-hole totals
    cutline = np.sort(tot2, axis=1)[:, min(69, k - 1)][:, None]
    made = tot2 <= cutline
    tot4 = tot2 + np.where(made, 2 * (mus + wk) + eps[:, :, 2:].sum(2), 1e6)
    order = tot4.argsort(1).argsort(1)                    # finishing rank per sim
    out = {}
    for i, p in enumerate(names):
        out[p] = {"win": float((order[:, i] == 0).mean()),
                  "top5": float((order[:, i] < 5).mean()),
                  "top10": float((order[:, i] < 10).mean()),
                  "top20": float((order[:, i] < 20).mean()),
                  "cut": float(made[:, i].mean())}
    return out


def walk_forward(seasons=(2025, 2026), verbose=True):
    """Validation that does NOT wait on odds. G2 needs settled matchup closes and sat at
    n=3 for weeks, which makes it unfalsifiable today. This scores the ruler against actual
    ROUND SCORES it never saw: for each event, fit strictly as-of its start date, then
    measure how well the predicted score ordering holds. Reported as pairwise accuracy
    (share of same-round player pairs where the better-rated player actually shot lower)
    plus RMSE against the field-relative score."""
    con = sqlite3.connect(DB)
    evs = con.execute("SELECT event_id, MIN(date) d, event FROM rounds GROUP BY event_id "
                      "HAVING d >= ? ORDER BY d", ("%d-01-01" % min(seasons),)).fetchall()
    con.close()
    import random
    random.seed(11)
    hits = tot = 0
    errs = []
    for eid, d0, ev in evs:
        R, _ = fit(asof=d0)
        Rn = {norm(k): v for k, v in R.items()}
        con = sqlite3.connect(DB)
        rows = con.execute("SELECT player, rnd, score FROM rounds WHERE event_id=?",
                           (eid,)).fetchall()
        con.close()
        by_r = defaultdict(list)
        for pl, rnd, sc in rows:
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


def g2_gate(verbose=True):
    """GATE G2 on REAL collected FanDuel 72-hole matchbet CLOSES: ruler log-loss vs the
    devigged close, on events whose results are now in the rounds table. The ruler is fit
    AS-OF each event's start date — no result it is judged on is inside its training set."""
    con = sqlite3.connect(LINES)
    mkts = con.execute(
        "SELECT event, market, runner, odds, MAX(collected_at) FROM golf_lines "
        "WHERE market LIKE '%Matchbet%' AND odds > 1.0 "
        "GROUP BY event, market, runner").fetchall()
    con.close()
    by_m = defaultdict(list)
    for evn, mkt, run, od, ts in mkts:
        by_m[(evn.strip(), mkt)].append((run, od, ts))
    conr = sqlite3.connect(DB)
    ll_book, ll_ruler, n_used = [], [], 0
    fits = {}
    for (evn, mkt), rr in by_m.items():
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
            continue
        ll_book.append(-(y * math.log(p_book) + (1 - y) * math.log(1 - p_book)))
        ll_ruler.append(-(y * math.log(p_rul) + (1 - y) * math.log(1 - p_rul)))
        n_used += 1
    if verbose:
        if n_used < 15:
            print(f"G2: only {n_used} gradeable closed matchups so far — gate INCONCLUSIVE, "
                  f"keep collecting (it self-answers as tournaments settle)")
        else:
            lb, lr = st.mean(ll_book), st.mean(ll_ruler)
            gap = (lr - lb) * 100
            verdict = "PASS" if gap <= 2.0 else "FAIL"
            print(f"G2 on {n_used} real FD closes: book logloss {lb:.4f}, ruler {lr:.4f} "
                  f"(gap {gap:+.1f}pts) -> {verdict}")
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
