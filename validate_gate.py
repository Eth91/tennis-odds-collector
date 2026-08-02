"""Validate the peer gate against tonight's four known outcomes before wiring it in."""
import wnba_tonight as T, wnba_wowy as W
from peer_gate import peer_stat_gate

pl = W.players()
inj = T.injuries()
def plays(n): return inj.get(n) not in ("Out", "Doubtful")
def logs(team, exclude):
    return {n: W.game_log(v["id"]) for n, v in pl.items()
            if (v.get("team") or "").upper() == team and n not in exclude and (v.get("gp") or 0) >= 5}

CASES = [
  # player, team, stat-label, valfn, line, dec, out-players, EXPECTED
  ("Olivia Nelson-Ododa","CON","rebounds",  lambda g: g["reb"],            6.5, 2.02, ["Brittney Griner","Aaliyah Edwards"], "SUPPRESS", 25.0),
  ("Breanna Stewart",    "NY", "reb_ast",   lambda g: g["reb"]+g["ast"],  12.5, 2.08, ["Marine Johannes","Leonie Fiebich","Satou Sabally"], "SUPPRESS", 35.7),
  ("Jordan Horston",     "SEA","rebounds",  lambda g: g["reb"],            3.5, 2.08, ["Dominique Malonga"], "PASS", 18.9),
  ("Marina Mabrey",      "TOR","rebounds",  lambda g: g["reb"],            3.5, 2.16, ["Isabelle Harrison","Nyara Sabally","Brittney Sykes"], "PASS", 31.0),
  ("Megan DiLeo",        "POR","points",    lambda g: g["pts"],           12.5, 1.82, ["Sarah Ashlee Barker"], "PASS", 27.0),
]
ok = 0
for name, team, lbl, vf, line, dec, outs, expect, pmin in CASES:
    blog = W.game_log(pl[name]["id"])
    tl = logs(team, set(outs) | {name})
    r = peer_stat_gate(blog, vf, line, dec, tl, plays, exclude=outs,
                       proj_min=pmin, mpg_of=lambda n: (pl.get(n) or {}).get("min"))
    got = "SUPPRESS" if r else "PASS"
    mark = "OK " if got == expect else "!! "
    ok += got == expect
    print("%s%-22s %-8s o%-5g @%.2f -> %-8s (expected %s)" % (mark, name, lbl, line, dec, got, expect))
    if r:
        print("      peer %s: with %d/%d=%.0f%%  without %d/%d=%.0f%%  breakeven %.0f%%" % (
            r["peer"], round(r["rate_with"]*r["n_with"]), r["n_with"], r["rate_with"]*100,
            round(r["rate_without"]*r["n_without"]), r["n_without"], r["rate_without"]*100,
            r["breakeven"]*100))
print("\n%d/%d cases correct" % (ok, len(CASES)))
