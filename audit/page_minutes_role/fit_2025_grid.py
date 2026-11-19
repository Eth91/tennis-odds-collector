import json, sys, itertools
from collections import defaultdict
rows = json.load(open(sys.argv[1]))
pb = lambda r: (min(int(r["pl10"] * 10) // 3, 3), 0 if r["l5"] < 10 else 1 if r["l5"] < 20 else 2)
cnt = defaultdict(lambda: [0, 0])
for r in rows:
    if not r["st"]:
        k = pb(r); cnt[k][0] += r["a"] > 0; cnt[k][1] += 1
PT = {k: v[0] / v[1] for k, v in cnt.items()}
def base(r, bu, bd, K):
    s = r["starts5"] / r["n5"] if r["n5"] else 0.0
    xs, prior = (r["s_last"], r["l5"] + bu * (1 - s)) if r["st"] else (r["b_last"], r["l5"] - bd * s)
    return min(40.0, (sum(xs) + K * prior) / (len(xs) + K))
by = defaultdict(list)
for r in rows:
    by[(r["gid"], r["team"])].append(r)
def run(bu, bd, K, norm, bump):
    out = []
    for g, rs in by.items():
        b = [base(r, bu, bd, K) for r in rs]
        if bump and rs[0]["xs"]:
            add = [0.0] * len(rs)
            for x, xm, xg in rs[0]["xs"]:
                w = [bb * (3.0 if r["grp"] and r["grp"] == xg else 1.0) for bb, r in zip(b, rs)]
                tw = sum(w)
                for i, r in enumerate(rs):
                    add[i] += xm * w[i] / tw * r["xsh"].get(str(x), 1.0) if tw else 0.0
            b = [min(40.0, x + a) for x, a in zip(b, add)]
        if norm == "N2":
            P = [1.0 if r["st"] else PT.get(pb(r), 0.9) for r in rs]
            c = 240 / sum(p * x for p, x in zip(P, b)); b = [x * c for x in b]
        out += [(r, min(40.0, x)) for r, x in zip(rs, b) if r["a"] > 0]
    return out
def score(out, sel=lambda r: True):
    o = [(r, x) for r, x in out if sel(r)]
    return round(sum(abs(x - r["a"]) for r, x in o) / len(o), 3), round(sum(x - r["a"] for r, x in o) / len(o), 3)
res = []
for norm, bump in (("N0", 0), ("N0", 1), ("N2", 0), ("N2", 1)):
    for bu, bd, K in itertools.product((6, 9, 12, 15), (3, 6, 9, 12), (2, 4, 6, 8)):
        res.append((score(run(bu, bd, K, norm, bump))[0], norm, bump, bu, bd, K))
res.sort()
best = {}
for x in res:
    best.setdefault((x[1], x[2]), x)
for k, x in sorted(best.items()):
    out = run(x[3], x[4], x[5], x[1], x[2])
    print(k, "best", x[3:], "all", score(out), "starters", score(out, lambda r: r["st"]), "bench", score(out, lambda r: not r["st"]))
print("top", res[:5])
