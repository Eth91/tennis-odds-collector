"""Does a COURSE reward specific SKILLS — and does WEATHER change which skill pays?

This is a different hypothesis from the one already tested and rejected. That test asked whether SG
adds to the rating as a MAIN effect (it does not: partials ~0, every blend hurt). This asks about
INTERACTIONS:
    does course C reward driving distance / accuracy / putting, beyond a player's overall skill?
    does a windy day at that same course shift the reward from accuracy toward distance?

DESIGN. The dependent variable is what our model MISSES:
    residual = (round score - that round's field mean) - our as-of rating
If a course rewards a skill, players strong in that skill should beat their own rating THERE.
Regressing on the residual rather than on raw score is what controls for overall ability — without
it, SG_OTT would just proxy for "is good at golf" and every course would look like it rewards
distance.

LEAK CONTROL: SG for a round in year Y uses seasons <= Y-1 only. Season SG for year Y is computed
from the very rounds being predicted.

THE REAL TEST is not whether any single course shows a coefficient — with ~100 courses, some will
by chance. It is whether the SPREAD of per-course coefficients EXCEEDS what sampling noise
predicts, the same empirical-Bayes logic that showed personal course fit was ~nil (true variance
0.0715 against 7.49 of round noise). A course-fit effect that cannot beat its own error bars is not
an effect.
"""
import math
import os
import shutil
import sqlite3
import statistics as st
from collections import defaultdict

import pga_ruler as RU

_SNAP = os.path.expanduser("~/pga_model_cf.sqlite")
shutil.copyfile(str(RU.DB), _SNAP)
RU.DB = _SNAP
CATS = ["SG_OTT", "SG_APP", "SG_ARG", "SG_PUTT"]


def _ckey(name):
    return " ".join(sorted(w for w in str(name or "").lower().split() if len(w) > 3))


def load():
    con = sqlite3.connect(_SNAP)
    sg = defaultdict(dict)                       # (player, year) -> {cat: avg}
    for yr, stat, player, avg in con.execute(
            "SELECT year, stat, player, avg FROM sg_stats WHERE avg IS NOT NULL"):
        sg[(RU.norm(player), yr)][stat] = avg
    evs = con.execute("SELECT event_id, event, MIN(date) FROM rounds GROUP BY event_id "
                      "ORDER BY MIN(date)").fetchall()
    con.close()
    return sg, evs


def sg_asof(sg, year, half_life_y=1.5):
    """Recency-weighted SG using ONLY seasons strictly before `year`."""
    acc = {}
    for (p, y), d in sg.items():
        if y >= year:
            continue
        w = 0.5 ** ((year - 1 - y) / half_life_y)
        a = acc.setdefault(p, {})
        for c, v in d.items():
            s = a.setdefault(c, [0.0, 0.0])
            s[0] += v * w
            s[1] += w
    return {p: {c: v[0] / v[1] for c, v in d.items() if v[1] > 0} for p, d in acc.items()}


def build():
    """[(course, year, player, residual, {cat: sg})] — the analysis table."""
    sg, evs = load()
    rows_all = RU.all_rows()
    out = []
    cache = {}
    for eid, evn, d0 in evs:
        try:
            yr = int(str(d0)[:4])
        except (TypeError, ValueError):
            continue
        if yr not in cache:
            cache[yr] = sg_asof(sg, yr)
        SG = cache[yr]
        if not SG:
            continue
        R, _ = RU.fit(asof=d0, rows=rows_all)
        Rn = {RU.norm(k): v for k, v in R.items()}
        con = sqlite3.connect(_SNAP)
        rr = con.execute("SELECT player, rnd, score FROM rounds WHERE event_id=? AND score>0",
                         (eid,)).fetchall()
        con.close()
        by = defaultdict(list)
        for pl, rnd, sc in rr:
            by[rnd].append((RU.norm(pl), sc))
        ck = _ckey(evn)
        for rnd, lst in by.items():
            if len(lst) < 40:
                continue
            fm = st.mean(s for _p, s in lst)
            for p, sc in lst:
                v = Rn.get(p)
                s = SG.get(p)
                if not v or not s:
                    continue
                if not all(c in s for c in CATS):
                    continue
                out.append((ck, yr, p, (sc - fm) - v[0], {c: s[c] for c in CATS}))
    return out


def lin(pairs):
    """slope, r, n for [(x, y)]."""
    if len(pairs) < 30:
        return None, None, len(pairs)
    xs = [a for a, _ in pairs]
    ys = [b for _, b in pairs]
    mx, my = st.mean(xs), st.mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if not den:
        return None, None, len(pairs)
    b = sum((x - mx) * (y - my) for x, y in pairs) / den
    sx, sy = st.pstdev(xs), st.pstdev(ys)
    r = (sum((x - mx) * (y - my) for x, y in pairs) / len(pairs) / (sx * sy)) if sx and sy else None
    return b, r, len(pairs)


if __name__ == "__main__":
    data = build()
    print("analysis rows (player-rounds with rating + prior-season SG): %d" % len(data))
    courses = defaultdict(list)
    for ck, _yr, _p, res, s in data:
        courses[ck].append((res, s))
    big = {c: v for c, v in courses.items() if len(v) >= 120}
    print("courses with >=120 such rounds: %d" % len(big))
    print()

    print("=== [1] MAIN EFFECT (sanity — expected ~0 after the earlier result) ===")
    print("    a negative slope means the skill BEATS its own rating on average")
    for c in CATS:
        b, r, n = lin([(s[c], res) for _ck, _y, _p, res, s in data])
        print("    %-8s slope %+.4f  r %+.3f  n=%d" % (c, b or 0, r or 0, n))

    print()
    print("=== [2] PER-COURSE COEFFICIENTS — does course fit by SKILL exist? ===")
    print("    real effect requires the SPREAD across courses to beat sampling noise")
    for c in CATS:
        betas, ses = [], []
        for ck, v in big.items():
            pts = [(s[c], res) for res, s in v]
            b, _r, n = lin(pts)
            if b is None:
                continue
            ys = [y for _x, y in pts]
            xs = [x for x, _y in pts]
            mx = st.mean(xs)
            den = sum((x - mx) ** 2 for x in xs)
            resid = st.pstdev(ys)
            se = (resid / math.sqrt(den)) if den > 0 else None
            if se and se > 0:
                betas.append(b)
                ses.append(se)
        if len(betas) < 12:
            print("    %-8s too few courses" % c)
            continue
        obs = st.pvariance(betas)
        noise = st.mean([s * s for s in ses])
        true = obs - noise
        verdict = ("REAL — spread beats noise" if true > 0.15 * noise
                   else "NOT DISTINGUISHABLE from noise")
        print("    %-8s %2d courses | observed var %.4f | sampling noise %.4f | true %+.4f -> %s"
              % (c, len(betas), obs, noise, true, verdict))
        if true > 0:
            print("             implied true sd of the course effect: %.3f strokes per unit SG"
                  % math.sqrt(true))
