"""Is the birdie miscalibration really the HOLE-MIX sensitivity, not players or the day factor?

Evidence pointing there: with every player collapsed to the field rate (D=0.01) the slope was still
0.551, and the measured beta-binomial day factor only lifts 0.608 -> 0.644. So what remains is how
strongly P(>=4) responds to the par mix. The model applies GLOBAL per-par rates — par3 .133, par4
.175, par5 .470 — but a par-5 at a US Open setup is nothing like a par-5 at a birdie-fest, so a
universal 0.470 over-states how much a mix change should move the count.

We now hold hole-level data for 114 events, so each COURSE's own per-par rates are measurable.
Test: recompute the leak-free reliability slope using course-specific par rates instead of global
ones. If the slope jumps, the mix sensitivity was the blocker.
"""
import os, shutil, sqlite3, statistics as st
from collections import defaultdict
import pga_birdies as B, pga_ruler as RU

_SNAP = os.path.expanduser("~/pga_model_cp.sqlite")
shutil.copyfile(str(RU.DB), _SNAP); RU.DB = _SNAP; B.DB = _SNAP
con = sqlite3.connect(_SNAP)
rows = con.execute("SELECT player, tid, tname, rnd, p3h, p3b, p4h, p4b, p5h, p5b "
                   "FROM birdie_rounds").fetchall()
con.close()

# global rates
tot = defaultdict(lambda: [0, 0])
# per-COURSE rates (token-normalised name, so editions of one course pool)
cr = defaultdict(lambda: defaultdict(lambda: [0, 0]))
def ckey(tn):
    return " ".join(sorted(w for w in str(tn or "").lower().split() if len(w) > 3))
for pl, tid, tn, rnd, a3, b3, a4, b4, a5, b5 in rows:
    for par, (h, b) in ((3, (a3, b3)), (4, (a4, b4)), (5, (a5, b5))):
        tot[par][0] += h or 0; tot[par][1] += b or 0
        cr[ckey(tn)][par][0] += h or 0; cr[ckey(tn)][par][1] += b or 0
g = {p: (v[1]/v[0] if v[0] else .15) for p, v in tot.items()}
# shrink each course's par rate toward global on hole count
K = 400.0
course_rate = {}
for c, d in cr.items():
    course_rate[c] = {}
    for par in (3, 4, 5):
        h, b = d[par]
        course_rate[c][par] = ((b + K * g[par]) / (h + K)) if h else g[par]
print("courses with own par rates: %d" % len(course_rate))
sp5 = [v[5] for v in course_rate.values()]
print("  par-5 birdie rate across courses: global %.3f | course range %.3f-%.3f (sd %.3f)"
      % (g[5], min(sp5), max(sp5), st.pstdev(sp5)))
sp4 = [v[4] for v in course_rate.values()]
print("  par-4 birdie rate across courses: global %.3f | course range %.3f-%.3f (sd %.3f)"
      % (g[4], min(sp4), max(sp4), st.pstdev(sp4)))

by_pl = defaultdict(list)
for pl, tid, tn, rnd, a3, b3, a4, b4, a5, b5 in rows:
    by_pl[RU.norm(pl)].append((str(tid), rnd, ckey(tn), a3 or 0, b3 or 0, a4 or 0, b4 or 0,
                               a5 or 0, b5 or 0))

def build(use_course):
    cells = []
    for pl, v in by_pl.items():
        if len(v) < 10: continue
        v.sort(key=lambda z: (z[0], z[1]))
        h = len(v) // 2
        # player's RELATIVE skill vs the courses he played in the early half
        num = {3: 0.0, 4: 0.0, 5: 0.0}; den = {3: 0.0, 4: 0.0, 5: 0.0}
        for _t, _r, ck, a3, b3, a4, b4, a5, b5 in v[:h]:
            base = course_rate.get(ck, g) if use_course else g
            for par, (hh, bb) in ((3, (a3, b3)), (4, (a4, b4)), (5, (a5, b5))):
                num[par] += bb; den[par] += hh * base[par]
        # multiplicative skill per par, shrunk
        skill = {}
        for par in (3, 4, 5):
            raw = (num[par] / den[par]) if den[par] > 0 else 1.0
            w = den[par] / (den[par] + 40.0)
            skill[par] = 1.0 + B.DISPERSION * w * (raw - 1.0)
        late = []
        for _t, _r, ck, a3, b3, a4, b4, a5, b5 in v[h:]:
            mixr = {3: a3, 4: a4, 5: a5}
            if sum(mixr.values()) < 15: continue
            base = course_rate.get(ck, g) if use_course else g
            rate = {par: min(base[par] * skill[par], .95) for par in (3, 4, 5)}
            late.append((rate, mixr, 1.0 if (b3 + b4 + b5) >= 4 else 0.0))
        if late: cells.append(late)
    return cells

def slope(cells, nb=10):
    preds, obs = [], []
    for late in cells:
        for rate, mixr, y in late:
            preds.append(B.p_x_or_more(rate, 4, mixr)); obs.append(y)
    srt = sorted(zip(preds, obs)); sz = len(srt)//nb; xs, ys = [], []
    for i in range(nb):
        ch = srt[i*sz:(i+1)*sz] if i < nb-1 else srt[i*sz:]
        if ch: xs.append(st.mean(c[0] for c in ch)); ys.append(st.mean(c[1] for c in ch))
    mx, my = st.mean(xs), st.mean(ys); den = sum((x-mx)**2 for x in xs)
    return ((sum((x-mx)*(y-my) for x, y in zip(xs, ys))/den) if den else 0,
            st.mean(preds), st.mean(obs), len(preds))

print()
print("  %-28s %8s %10s %10s %8s" % ("per-par rates", "slope", "pred", "real", "n"))
for lbl, uc in (("GLOBAL (current model)", False), ("COURSE-SPECIFIC", True)):
    sl, pm, rm, n = slope(build(uc))
    print("  %-28s %8.3f %10.4f %10.4f %8d" % (lbl, sl, pm, rm, n))
