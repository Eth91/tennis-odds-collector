"""NBA_UNDER_PREREG.md amendment 7: the pinged unders (30-50% below, -150 or better, not threes) with and without players
getting a minutes bump from a teammate's absence (post-hoc; information)."""
import sys
import numpy as np
sys.path.insert(0, ".")
exec(open("nba_tests4_checks.py").read().split("NAMES = [")[0])   # builds seasons, rows (with ctx), lines, fd
rng = np.random.default_rng(7)

CUTS = {
    "B1 new starter": lambda f: f["b1"],
    "B2 starter out": lambda f: f["b2"],
    "B3 same-position teammate out": lambda f: f["b3"],
    "B4 our projection +3 min": lambda f: f["b4"],
    "any of B1-B3 (injury bump)": lambda f: f["b1"] or f["b2"] or f["b3"],
    "hindsight: played 5+ over his last-10": lambda f: f["hind"],
}

flags = {s: [] for s in rows}
for s in rows:
    bd = seasons[s].bd
    for r in rows[s]:
        team, d, p, box = r["team"], r["date"], r["pid"], r["team_box"]
        cand = []
        for mk in T.MARKETS:
            ln = lines.get((d, p, mk))
            if not ln or mk == "threes":
                continue
            line, _over, under, _q = ln
            act = BOOST.stat_of(r["box"], mk)
            below = 1 - T.proj(r, mk) / line
            if act == line or under < 1 / 0.6 - 1e-9 or not 0.30 <= below < 0.50:
                continue
            fdu = fd.get((d, p, mk, line), {}).get("under")
            cand.append({"mk": mk, "u": under - 1 if act < line else -1.0,
                         "u_fd": (fdu - 1 if act < line else -1.0) if fdu else None})
        if not cand:
            continue
        played = {q for q, x in box.items() if x["min"]}
        starters = bd.usual_five(team, d) or bd.starters(team, d)
        out_all = (bd.on_team_tonight(team, d) - played) & (bd.roster(team, d) | starters)
        last10 = r["min"] - r["ctx"]["min_change"]
        tags = {"b1": bool(r["new_starter"]), "b2": r["n_out"] >= 1,
                "b3": any((pg := bd.per_game(x, team, d)) and pg["min"] >= 20 and bd.letters(x) & bd.letters(p) for x in out_all),
                "b4": r["ctx"]["min_change"] >= 3, "hind": r["box"]["min"] >= last10 + 5}
        flags[s] += [{**c, **tags} for c in cand]


def show(vals):
    v = np.array(vals)
    if len(v) < 20:
        return f"n {len(v):4d}          "
    bs = np.sort([rng.choice(v, len(v)).mean() for _ in range(1000)])
    return f"n {len(v):4d} ROI {v.mean():+.3f} [{bs[50]:+.3f},{bs[950]:+.3f}]"


for price in ("u", "u_fd"):
    print(f"\n== {'best FanDuel/DraftKings' if price == 'u' else 'FanDuel own'} under price; 30-50% below, -150 or better, not threes")
    for s in flags:
        fs = [f for f in flags[s] if f[price] is not None]
        print(f" {s}  all: {show([f[price] for f in fs])}")
        for name, cut in CUTS.items():
            print(f"   {name:38s} excluded: {show([f[price] for f in fs if not cut(f)])}   only: {show([f[price] for f in fs if cut(f)])}")
