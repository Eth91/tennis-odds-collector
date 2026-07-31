"""⛳ Golf-logic learning engine — finds WHY rounds went wrong, and proposes; it never applies.

WHAT THIS IS NOT. It is not a system that retrains the model after every round. That is the single
failure mode this project has already paid for three times: MLB pitcher props were retired for it,
the PGA edges were forensically debunked as artifacts of it, and WNBA took 132 logic changes against
151 graded bets before it had to be frozen. A slate produces ~10 bets. Nothing that adapts itself on
10 bets is learning; it is fitting noise with confidence.

THE RESTATEMENT THAT MAKES IT WORK. Our losses are the PROMPT. The EVIDENCE is the field: ~150
players x 18 holes every round, already harvested — 42,581 player-rounds across 114 events. That is
where the statistical power lives. H-P1 came out of exactly this move: a question raised by seven
losing bets, answered on 27,756 independent round-pairs.

So each round this engine:
  1. recomputes the de-conditioned residual for EVERY player in the field, not just the ones we bet;
  2. tests a registry of golf-logic hypotheses against the whole accumulated history;
  3. reports which survive, with n, effect size, a null, and leave-one-event-out stability;
  4. separately profiles OUR losing bets against those same features, so the prompt is visible;
  5. writes candidates into the evidence file — and stops. Adoption stays a human decision under the
     freeze, which is the only thing that has ever prevented this project from fitting noise.

THE RESIDUAL, and why conditions come out first. A course plays harder or easier round to round —
measured, the field's birdie rate ranges 0.88x to 1.13x of its own event average. Correlate anything
against raw birdie counts and you will mostly rediscover the weather. So:

    round_factor(event, rnd) = field rate that round / field rate that event
    expected(player, rnd)    = player's LEAVE-ONE-EVENT-OUT rate * round_factor
    residual                 = actual - expected

Every hypothesis is scored against that residual, never against raw output.

WHAT COUNTS AS SURVIVING. A feature is only reported as a candidate when it clears all four:
    |r| >= MIN_R           an effect worth acting on
    n >= MIN_N             enough independent player-rounds
    |null| <= NULL_MAX     the shuffled control is flat, so conditions really did come out
    sign stable across leave-one-event-out folds
Anything else is listed as "not supported" WITH its numbers, because a null result recorded is worth
more than a null result forgotten — this is how a hypothesis stops being re-proposed every month.

    python3 pga_learn.py            report on everything accumulated
    python3 pga_learn.py --round    same, plus a profile of our most recent flagged losses
"""
import datetime as dt
import json
import math
import random
import sqlite3
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL_DB = HERE / "pga_model.sqlite"
TEES_DB = HERE / "pga_tees.sqlite"
PAPER_DB = HERE / "pga_paper.sqlite"
REPORT = HERE / "PGA_LEARN.md"
STATE = HERE / "pga_learn.json"

MIN_R = 0.05          # smaller than this cannot move a birdie line meaningfully
MIN_N = 400           # player-rounds
NULL_MAX = 0.02       # the shuffled control must be flat
MIN_HOLES = 17        # drop partial rounds: a WD is not a bad round


# ── data ──────────────────────────────────────────────────────────────────────
def _rounds():
    """[(tid, tname, player, rnd, holes, birdies)] over complete rounds."""
    con = sqlite3.connect(MODEL_DB)
    rows = [r for r in con.execute(
        "SELECT tid, tname, player, rnd, "
        "COALESCE(p3h,0)+COALESCE(p4h,0)+COALESCE(p5h,0), "
        "COALESCE(p3b,0)+COALESCE(p4b,0)+COALESCE(p5b,0), "
        "COALESCE(p3h,0), COALESCE(p3b,0), COALESCE(p4h,0), COALESCE(p4b,0), "
        "COALESCE(p5h,0), COALESCE(p5b,0) FROM birdie_rounds")]
    con.close()
    return [r for r in rows if (r[4] or 0) >= MIN_HOLES]


def residuals(rows):
    """{(tid, player, rnd): residual} — de-conditioned, leave-one-event-out baseline."""
    rate = {(t, p, int(r)): b / h for t, _tn, p, r, h, b, *_ in rows}
    by_ev_rnd, by_ev, allv = defaultdict(list), defaultdict(list), []
    for (t, p, r), v in rate.items():
        by_ev_rnd[(t, r)].append(v)
        by_ev[t].append(v)
        allv.append(v)
    # TWO levels of conditions, not one. Removing only the ROUND level is what manufactured H-P1:
    # event factors span 0.81-1.24, so a week playing easy against a player's history lifts ALL
    # their residuals that week, and any within-event feature then "predicts" for reasons that have
    # nothing to do with the player. Round factor alone cannot see this, because it normalises each
    # round to the EVENT mean and so is blind to where that mean sits.
    grand = st.mean(allv) if allv else 1.0
    efac = {t: (st.mean(v) / grand if grand else 1.0) for t, v in by_ev.items()}
    rfac = {}
    for (t, r), v in by_ev_rnd.items():
        base = st.mean(by_ev[t]) or 1e-9
        rfac[(t, r)] = st.mean(v) / base if base else 1.0
    tot, per_ev = defaultdict(lambda: [0.0, 0]), defaultdict(lambda: [0.0, 0])
    for (t, p, r), v in rate.items():
        tot[p][0] += v
        tot[p][1] += 1
        per_ev[(p, t)][0] += v
        per_ev[(p, t)][1] += 1
    out = {}
    for (t, p, r), v in rate.items():
        s, n = tot[p]
        es, en = per_ev[(p, t)]
        s, n = s - es, n - en                      # this event never informs its own baseline
        if n < 4:
            continue
        f = rfac.get((t, r))
        if not f:
            continue
        out[(t, p, r)] = v - (s / n) * f * efac.get(t, 1.0)
    return out, rate, rfac


# ── context tables the features draw on ──────────────────────────────────────
def _tees():
    """{(tid, rnd, player_lower): tee_ms} and the median tee that round."""
    idx, byr = {}, defaultdict(list)
    try:
        c = sqlite3.connect(TEES_DB)
        for tid, rnd, pl, ms, stt in c.execute(
                "SELECT tid, rnd, player, tee_ms, start_tee FROM tee_sheet WHERE tee_ms IS NOT NULL"):
            idx[(str(tid), int(rnd or 0), str(pl).lower())] = (float(ms), stt)
            byr[(str(tid), int(rnd or 0))].append(float(ms))
        c.close()
    except sqlite3.Error:
        pass
    med = {k: st.median(v) for k, v in byr.items() if v}
    return idx, med


def _scores():
    """{(event_lower, player_lower, rnd): score} and each event's per-round field mean."""
    sc, fld = {}, defaultdict(list)
    try:
        c = sqlite3.connect(MODEL_DB)
        for ev, pl, rnd, s in c.execute(
                "SELECT event, player, rnd, score FROM rounds WHERE score IS NOT NULL"):
            k = (str(ev).lower(), str(pl).lower(), int(rnd or 0))
            sc[k] = float(s)
            fld[(str(ev).lower(), int(rnd or 0))].append(float(s))
    except sqlite3.Error:
        pass
    return sc, {k: st.mean(v) for k, v in fld.items() if v}


def _sg():
    """{player_lower: {stat: avg}} — strokes gained by category, the known blind spot."""
    out = defaultdict(dict)
    try:
        c = sqlite3.connect(MODEL_DB)
        for pl, stat, avg in c.execute("SELECT player, stat, avg FROM sg_stats WHERE avg IS NOT NULL"):
            out[str(pl).lower()][str(stat)] = float(avg)
        c.close()
    except sqlite3.Error:
        pass
    return out


def _course_par5():
    """{tid: share of holes that are par 5} — for the par-mix interaction."""
    out = {}
    try:
        c = sqlite3.connect(MODEL_DB)
        for tid, n5, n in c.execute(
                "SELECT tid, SUM(CASE WHEN par=5 THEN 1 ELSE 0 END), COUNT(*) "
                "FROM course_holes GROUP BY tid"):
            if n:
                out[str(tid)] = (n5 or 0) / n
        c.close()
    except sqlite3.Error:
        pass
    return out


CTX = {}


def _ctx():
    if not CTX:
        CTX["tee"], CTX["tee_med"] = _tees()
        CTX["score"], CTX["field"] = _scores()
        CTX["sg"] = _sg()
        CTX["par5"] = _course_par5()
    return CTX


# ── the hypothesis registry ──────────────────────────────────────────────────
# Each entry: name -> (extractor(row, rows_by_key) -> float|None, golf rationale).
# A feature must be knowable BEFORE the round it is scored against, or it is not a signal.
def f_wave(row, R):
    """Tee-time wave. Greens are fresh and calm in the morning and beaten up by the afternoon;
    on windy days the split can be worth a stroke or more."""
    c = _ctx()
    tid, pl, rnd = row
    t = c["tee"].get((tid, rnd, pl.lower()))
    m = c["tee_med"].get((tid, rnd))
    if not t or not m:
        return None
    return 1.0 if t[0] > m else -1.0            # +1 = afternoon


def f_tee_slot(row, R):
    """Position within the day, continuous — the first and last groups sit in different courses."""
    c = _ctx()
    tid, pl, rnd = row
    t = c["tee"].get((tid, rnd, pl.lower()))
    day = [v[0] for (a, b, _p), v in c["tee"].items() if a == tid and b == rnd] \
        if False else None
    m = c["tee_med"].get((tid, rnd))
    if not t or not m:
        return None
    return (t[0] - m) / (3.6e6 * 3.0)           # hours from the median tee, /3


def f_start_tee(row, R):
    """Starting from the 10th rather than the 1st: a different hole sequence, and on many courses
    the closing stretch is the harder one, so a 10th-tee start finishes on the easier nine."""
    c = _ctx()
    tid, pl, rnd = row
    t = c["tee"].get((tid, rnd, pl.lower()))
    if not t or t[1] is None:
        return None
    return 1.0 if int(t[1]) == 10 else -1.0


def f_round_no(row, R):
    """Round number. Weekend fields are cut to the players in form, and pins are traditionally
    tougher on Sunday."""
    return float(row[2])


def f_prev_residual(row, R):
    """The H-P1 control. This is ALREADY validated at r=+0.152, so it is the harness's own test:
    if the engine cannot recover it, the engine is broken and nothing else it says can be trusted."""
    tid, pl, rnd = row
    return R.get((tid, pl, rnd - 1)) if rnd > 1 else None


def f_days_rest(row, R):
    """Days since the player's last competitive round. Rust versus fatigue is a genuine golf
    argument and it should be settled by data rather than by assertion."""
    c = _ctx()
    return None if not c else None                # needs event dates per tid; see _scores TODO


def f_cut_pressure(row, R):
    """Round 2 only: strokes from the projected cut going into the round. Players on the number
    press for birdies; players safely inside protect. Both change birdie rate."""
    c = _ctx()
    tid, pl, rnd = row
    if rnd != 2:
        return None
    ev = _tid_event(tid)
    if not ev:
        return None
    s1 = c["score"].get((ev, pl.lower(), 1))
    f1 = c["field"].get((ev, 1))
    if s1 is None or f1 is None:
        return None
    return s1 - f1                                # + = behind the field after R1


def f_position(row, R):
    """Cumulative strokes to the field entering this round — leaders protect, chasers attack."""
    c = _ctx()
    tid, pl, rnd = row
    if rnd < 2:
        return None
    ev = _tid_event(tid)
    if not ev:
        return None
    d = 0.0
    seen = 0
    for r in range(1, rnd):
        s = c["score"].get((ev, pl.lower(), r))
        f = c["field"].get((ev, r))
        if s is None or f is None:
            continue
        d += s - f
        seen += 1
    return d if seen else None


def f_par5_fit(row, R):
    """Interaction: a player's par-5 birdie skill against how par-5-heavy the course is. Par 5s are
    where birdies are cheapest, so a long player's edge should be larger where there are more."""
    c = _ctx()
    tid, pl, rnd = row
    share = c["par5"].get(tid)
    sk = _PAR5_SKILL.get(pl)
    if share is None or sk is None:
        return None
    return sk * (share - 0.222)                   # 0.222 = 4 par 5s in 18


def f_sg(stat):
    def _f(row, R):
        c = _ctx()
        return c["sg"].get(row[1].lower(), {}).get(stat)
    _f.__doc__ = ("Strokes gained: %s. The DataGolf audit named SG-by-category the model's single "
                  "biggest blind spot; if any of these predicts the residual, the model is leaving "
                  "known information on the table." % stat)
    return _f


_TID_EVENT = {}
_PAR5_SKILL = {}


def _tid_event(tid):
    return _TID_EVENT.get(tid)


HYPOTHESES = {
    "prev_round_residual (H-P1 control)": f_prev_residual,
    "wave (PM vs AM)": f_wave,
    "tee slot (hours from median)": f_tee_slot,
    "start tee (10th vs 1st)": f_start_tee,
    "round number": f_round_no,
    "cut pressure (R2)": f_cut_pressure,
    "position vs field entering round": f_position,
    "par-5 skill x course par-5 share": f_par5_fit,
}


# ── the test harness ─────────────────────────────────────────────────────────
def _corr(pairs):
    if len(pairs) < 12:
        return None
    xs = [a for a, _ in pairs]
    ys = [b for _, b in pairs]
    mx, my = st.mean(xs), st.mean(ys)
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if not dx or not dy:
        return None
    return sum((a - mx) * (b - my) for a, b in pairs) / (dx * dy)


def evaluate(name, fn, resid, rows):
    pairs, keys = [], []
    for (tid, pl, rnd), res in resid.items():
        try:
            v = fn((tid, pl, rnd), resid)
        except Exception:                                          # noqa: BLE001
            v = None
        if v is None:
            continue
        pairs.append((float(v), res))
        keys.append(tid)
    r = _corr(pairs)
    if r is None:
        return {"name": name, "n": len(pairs), "r": None, "null": None,
                "stable": None, "effect": None}
    # NULL: shuffle the feature WITHIN (event, round) so conditions are preserved exactly and only
    # the player-to-feature link is broken. A non-flat null means the de-conditioning leaked.
    rng = random.Random(17)
    byg = defaultdict(list)
    for i, ((v, res), tid) in enumerate(zip(pairs, keys)):
        byg[tid].append(i)
    sh = list(pairs)
    for g, idxs in byg.items():
        vals = [pairs[i][0] for i in idxs]
        rng.shuffle(vals)
        for i, v in zip(idxs, vals):
            sh[i] = (v, pairs[i][1])
    null = _corr(sh)
    # STABILITY: leave one event out, does the sign hold?
    evs = sorted({k for k in keys})
    signs = []
    for e in evs[:40]:
        sub = [p for p, k in zip(pairs, keys) if k != e]
        c = _corr(sub)
        if c is not None:
            signs.append(c)
    stable = bool(signs) and all((c > 0) == (r > 0) for c in signs)
    sd = st.pstdev([b for _, b in pairs]) if len(pairs) > 2 else 0.0
    return {"name": name, "n": len(pairs), "r": r, "null": null, "stable": stable,
            "effect": abs(r) * sd * 18}


def _load_par5_skill(rows):
    agg = defaultdict(lambda: [0, 0])
    for _t, _tn, pl, _r, _h, _b, _p3h, _p3b, _p4h, _p4b, p5h, p5b in rows:
        agg[pl][0] += p5h
        agg[pl][1] += p5b
    lg = (sum(v[1] for v in agg.values()) / max(sum(v[0] for v in agg.values()), 1))
    for pl, (h, b) in agg.items():
        if h >= 40:
            _PAR5_SKILL[pl] = (b / h) - lg


def _load_tid_event():
    try:
        c = sqlite3.connect(MODEL_DB)
        for tid, tn in c.execute("SELECT DISTINCT tid, tname FROM birdie_rounds"):
            _TID_EVENT[str(tid)] = str(tn or "").lower()
        c.close()
    except sqlite3.Error:
        pass


# ── our own losses: the prompt, not the evidence ─────────────────────────────
def loss_profile():
    """Where our LOSING flags sat on each feature, versus our winners.

    This is deliberately separated from the statistics above and never drives a verdict: at ~10 bets
    a round it can only ever raise a question. The answer comes from the field."""
    try:
        c = sqlite3.connect(PAPER_DB)
        rows = [dict(zip([d[0] for d in c.description], r)) for r in c.execute(
            "SELECT market, runner, result, p_bet, p_fair, odds FROM flags "
            "WHERE result IN ('W','L')")]
        c.close()
    except sqlite3.Error:
        return []
    return rows


def report(with_round=False):
    rows = _rounds()
    _load_par5_skill(rows)
    _load_tid_event()
    resid, _rate, _rfac = residuals(rows)
    L = ["# ⛳ PGA golf-logic learning report", "",
         "_%s · %d player-rounds, %d events · PROPOSES ONLY, never applies_"
         % (dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            len(rows), len({r[0] for r in rows})), "",
         "Residuals are de-conditioned at the round level and use leave-one-event-out baselines, so "
         "a course playing harder or easier cannot masquerade as a finding. Every hypothesis below "
         "is scored against that residual, never against raw birdie counts.", "",
         "A candidate must clear ALL of: |r| >= %.2f, n >= %d, |null| <= %.2f, and a sign that "
         "survives leave-one-event-out. Results that fail are listed too — a recorded null is what "
         "stops a dead idea being re-proposed every month." % (MIN_R, MIN_N, NULL_MAX), ""]
    res = []
    for name, fn in HYPOTHESES.items():
        res.append(evaluate(name, fn, resid, rows))
    res.sort(key=lambda d: -(abs(d["r"]) if d["r"] is not None else -1))

    L += ["| hypothesis | n | r | null | stable | effect (birdies/18) | verdict |",
          "|---|---|---|---|---|---|---|"]
    cands = []
    for d in res:
        if d["r"] is None:
            L.append("| %s | %d | – | – | – | – | insufficient data |" % (d["name"], d["n"]))
            continue
        ok = (abs(d["r"]) >= MIN_R and d["n"] >= MIN_N
              and abs(d["null"] or 0) <= NULL_MAX and d["stable"])
        verdict = "**CANDIDATE**" if ok else "not supported"
        if ok:
            cands.append(d)
        L.append("| %s | %d | %+.3f | %+.3f | %s | %.2f | %s |"
                 % (d["name"], d["n"], d["r"], d["null"] or 0,
                    "yes" if d["stable"] else "no", d["effect"] or 0, verdict))
    L += ["", "## Candidates", ""]
    if cands:
        for d in cands:
            L.append("- **%s** — r=%+.3f on n=%d, null %+.3f, sign stable across events, worth "
                     "~%.2f birdies per 18. NOT adopted: it must clear the paired-SPRT rule on "
                     "prospective data like any other change."
                     % (d["name"], d["r"], d["n"], d["null"] or 0, d["effect"] or 0))
    else:
        L.append("_None cleared the bar this run._")

    if with_round:
        lp = loss_profile()
        L += ["", "## Our own flagged bets (the prompt, not the evidence)", ""]
        if lp:
            w = [r for r in lp if r["result"] == "W"]
            l = [r for r in lp if r["result"] == "L"]
            L += ["Settled: **%d-%d**." % (len(w), len(l)), "",
                  "| | mean model p | mean market p |", "|---|---|---|"]
            for lab, g in (("winners", w), ("losers", l)):
                if g:
                    L.append("| %s | %.3f | %.3f |"
                             % (lab, sum(x["p_bet"] or 0 for x in g) / len(g),
                                sum(x["p_fair"] or 0 for x in g) / len(g)))
            L += ["", "At this sample size this can only raise questions. Anything it suggests has "
                  "to be answered against the field above before it means anything.", ""]
        else:
            L.append("_No settled flags yet._")

    L += ["", "## Standing rule", "",
          "This engine proposes. It does not tune, retrain, or adopt. Every candidate enters the "
          "evidence file as a hypothesis and must beat the frozen baseline on PROSPECTIVE data. "
          "Automated self-modification on ~10 bets a round is the failure that retired MLB, "
          "manufactured the original PGA edges, and forced the WNBA freeze after 132 logic changes "
          "against 151 graded bets.", ""]
    REPORT.write_text("\n".join(L), encoding="utf-8")
    STATE.write_text(json.dumps({"updated": dt.datetime.utcnow().isoformat(),
                                 "results": res, "candidates": [c["name"] for c in cands]},
                                indent=1, default=str), encoding="utf-8")
    print("\n".join(L))
    return res


if __name__ == "__main__":
    report(with_round="--round" in sys.argv)
