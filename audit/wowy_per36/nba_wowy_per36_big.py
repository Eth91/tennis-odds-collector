"""NBA_WOWY_PER36_PREREG.md amendment 2: 40% and 50% thresholds, both seasons pooled.
    python3 per36_big.py"""
import json

import per36_test as P
import per36_pct as Q

X = (.40, .50)

if __name__ == "__main__":
    eng = P.engine_minutes()
    ev = []
    for s in P.LINE_SEASONS:
        ev += P.events_for(s, eng)[0]
    L = {}
    for s in P.LINE_SEASONS:
        L.update(P.lines(s)[0])
    res = {}
    for r in ("W", "O"):
        for m in P.MINS:
            for k in P.MK:
                for x in X:
                    for side in ("over", "under"):
                        c = (r, m, k, x, side)
                        by = {s: Q.bets(ev, L, s, c) for s in P.LINE_SEASONS}
                        a, b = P.summ(by["2023-24"]), P.summ(by["2024-25"])
                        pooled = P.summ([(s + g, *rest) for s in P.LINE_SEASONS for g, *rest in by[s]], ci=True)
                        both = a["n"] and b["n"] and a["roi"] > 0 and b["roi"] > 0
                        v = "PASS" if both and pooled["ci"][0] > 0 else "PROMISING" if both else "FAIL"
                        res[f"{r}x{m} {k} {side} {int(x * 100)}%"] = {"2023-24": a, "2024-25": b, "pooled": pooled, "verdict": v}
    json.dump(res, open(P.HERE + "per36_big_result.json", "w"), indent=1)
    for n, v in res.items():
        a, b, p = v["2023-24"], v["2024-25"], v["pooled"]
        print(f"{n:26s} 23-24 n {a['n']:4d} {a.get('roi', 0):+.3f} | 24-25 n {b['n']:4d} {b.get('roi', 0):+.3f} | pooled "
              f"{p.get('roi', 0):+.3f} {p.get('ci')} hit {p.get('hit')} -> {v['verdict']}")
