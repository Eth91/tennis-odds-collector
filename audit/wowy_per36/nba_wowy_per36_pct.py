"""NBA_WOWY_PER36_PREREG.md amendment 1 (cf24c7c73d): percentage thresholds.
    python3 per36_pct.py"""
import json

import per36_test as P

X = (.10, .15, .20, .25, .30)
RATES = ("W", "O")


def bets(ev, L, s, combo):
    r, m, k, x, side = combo
    out = []
    for e in ev:
        key = (e["gid"], e["x"], k)
        if e["season"] != s or key not in L:
            continue
        p = P.proj(e, r, m, k)
        if p is None:
            continue
        ln, po, pu, _ = L[key]
        if (side == "over" and p >= (1 + x) * ln) or (side == "under" and p <= (1 - x) * ln):
            v = e["g"][k]
            win = v > ln if side == "over" else v < ln
            out.append((e["gid"], 0.0 if v == ln else ((po if side == "over" else pu) - 1 if win else -1.0), win, v != ln))
    return out


if __name__ == "__main__":
    eng = P.engine_minutes()
    ev = []
    for s in P.LINE_SEASONS:
        ev += P.events_for(s, eng)[0]
    L = {}
    for s in P.LINE_SEASONS:
        L.update(P.lines(s)[0])
    combos = [(r, m, k, x, side) for r in RATES for m in P.MINS for k in P.MK for x in X for side in ("over", "under")]
    name = lambda c: f"{c[0]}x{c[1]} {c[2]} {c[4]} {int(c[3] * 100)}%"
    disc = {c: P.summ(bets(ev, L, "2023-24", c)) for c in combos}
    conf_all = {c: P.summ(bets(ev, L, "2024-25", c)) for c in combos}
    ranked = sorted((c for c in combos if disc[c]["n"] >= 100 and disc[c]["roi"] > 0), key=lambda c: -disc[c]["roi"])
    carried = {}
    for c in ranked[:3]:
        cc = P.summ(bets(ev, L, "2024-25", c), ci=True)
        v = "PASS" if cc["n"] and cc["ci"][0] > 0 else "PROMISING" if cc["n"] and cc["roi"] > .03 else "FAIL"
        carried[name(c)] = {"2023-24": disc[c], "2024-25": cc, "verdict": v}
    res = {"n_disc_qualifying": len(ranked), "discovery_top10": [[name(c), disc[c], conf_all[c]] for c in ranked[:10]],
           "carried": carried, "W_all": {name(c): {"2023-24": disc[c], "2024-25": conf_all[c]} for c in combos if c[0] == "W"},
           "O_all": {name(c): {"2023-24": disc[c], "2024-25": conf_all[c]} for c in combos if c[0] == "O"}}
    json.dump(res, open(P.HERE + "per36_pct_result.json", "w"), indent=1)
    print("discovery qualifying", len(ranked))
    for n_, a, b in res["discovery_top10"]:
        print(f"  disc {n_:26s} 23-24 {a}  | 24-25 {b}")
    for n_, v in carried.items():
        print("CARRIED", n_, v)
    for k in P.MK:
        for side in ("over", "under"):
            print(k, side)
            for c in combos:
                if c[2] == k and c[4] == side and c[0] == "W":
                    a, b = disc[c], conf_all[c]
                    print(f"   {name(c):26s} 23-24 n {a['n']:5d} roi {a.get('roi', 0):+.3f} | 24-25 n {b['n']:5d} roi {b.get('roi', 0):+.3f}")
