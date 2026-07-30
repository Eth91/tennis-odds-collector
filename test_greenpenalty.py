"""Is the green-penalty index wired in — and does it EARN being wired in?

It is not wired: nothing imports pga_holes. It is a derived feature sitting in a module.

The index exists to answer one question that every previous course-fit attempt failed to answer
honestly, because they inferred the course characteristic from the same residuals they then tested
against. This one MEASURES the course (par-3 bogey share from real hole outcomes), so the test is
clean: do good putters actually beat their rating on penal greens?

If SG_PUTT x green_penalty is null too, the index does not go in — a face-valid feature that
predicts nothing is still a feature that predicts nothing.
"""
import os
import sqlite3
import statistics as st

import pga_holes as H

IX = os.path.expanduser("~/pga_interactions.sqlite")
SKILLS = ["SG_PUTT", "SG_ARG", "SG_APP", "SG_OTT", "SCRAMBLE", "GIR"]

feat = H.course_features()
gp = {k: v["green_penalty"] for k, v in feat.items() if v.get("green_penalty") is not None}
print("courses with a green-penalty index: %d" % len(gp))

con = sqlite3.connect(IX)
cols = ["course", "year", "resid"] + SKILLS
rows = con.execute("SELECT %s FROM ix" % ",".join(cols)).fetchall()
con.close()
idx = {c: i for i, c in enumerate(cols)}

# the two tables key courses differently (birdie tname vs ESPN event name), so match on token
# overlap rather than assuming the keys are identical
def match(ck):
    if ck in gp:
        return gp[ck]
    a = set(ck.split())
    best, bs = None, 0
    for k, v in gp.items():
        b = set(k.split())
        if not a or not b:
            continue
        j = len(a & b) / len(a | b)
        if j > bs:
            best, bs = v, j
    return best if bs >= 0.5 else None


joined = 0
pts = {s: [] for s in SKILLS}
gvals = []
cache = {}
for r in rows:
    ck = r[idx["course"]]
    if ck not in cache:
        cache[ck] = match(ck)
    g = cache[ck]
    if g is None:
        continue
    joined += 1
    gvals.append(g)
    for s in SKILLS:
        v, res = r[idx[s]], r[idx["resid"]]
        if v is not None and res is not None:
            pts[s].append((g, v, res))
print("rows joined to a green-penalty value: %d (%.0f%%)" % (joined, 100 * joined / len(rows)))
if gvals:
    print("  green_penalty over joined rows: mean %.3f sd %.3f" % (st.mean(gvals), st.pstdev(gvals)))


def corr(p):
    if len(p) < 300:
        return None, len(p)
    xs = [a for a, _ in p]
    ys = [b for _, b in p]
    mx, my = st.mean(xs), st.mean(ys)
    sx, sy = st.pstdev(xs), st.pstdev(ys)
    if not sx or not sy:
        return None, len(p)
    return sum((a - mx) * (b - my) for a, b in p) / len(p) / (sx * sy), len(p)


print()
print("=== DOES A PENAL GREEN COMPLEX REWARD THE SKILLS IT SHOULD? ===")
print("    r < 0 : the skill OUTperforms its rating as greens get more penal (an edge)")
print("    %-10s %10s %9s" % ("skill", "r", "n"))
gm = st.mean(gvals) if gvals else 0
gs = st.pstdev(gvals) if gvals else 1
best = None
for s in SKILLS:
    v = [p[1] for p in pts[s]]
    if len(v) < 300:
        continue
    vm, vs = st.mean(v), (st.pstdev(v) or 1)
    r, n = corr([(((g - gm) / gs) * ((x - vm) / vs), res) for g, x, res in pts[s]])
    if r is None:
        continue
    flag = "  <- candidate" if abs(r) >= 0.03 else ""
    print("    %-10s %+10.4f %9d%s" % (s, r, n, flag))
    if best is None or abs(r) > abs(best[1]):
        best = (s, r)
print()
if best and abs(best[1]) >= 0.03:
    print("    candidate: %s (r=%+.4f) — needs an out-of-sample check before wiring" % best)
else:
    print("    NOTHING reaches |r|>=0.03. The index is face-valid and measures a real course")
    print("    property, but it does NOT predict who beats their rating. It stays UNWIRED —")
    print("    a feature that describes the world but not the residual is not an edge.")
