"""Does Carleton actually shoot MORE with Barker out? Test the claim on its own terms.

"Same minutes but shoots more" is a usage claim, and usage is not FGA alone — a trip to the line is
a scoring possession too. So compare FGA, FTA, the two combined, and the per-minute rate, and show
the individual games rather than only the means, because n_without here is 2 and a mean of two
numbers hides everything that matters about it.
"""
import wnba_wowy as W

OUT_PID, OUT_NAME = 4703794, "Sarah Ashlee Barker"
PEOPLE = (("Bridget Carleton", 3906972), ("Megan DiLeo", 3934218))
out_log = W.game_log(OUT_PID)
out_dates = {g["date"][:10] for g in out_log}
all_dates = {g["date"][:10] for g in out_log}

for name, pid in PEOPLE:
    log = W.game_log(pid)
    w = W.wowy(log, out_log)
    print("\n" + "=" * 78)
    print("=== %s   (games WITHOUT %s: %s) ===" % (name, OUT_NAME, w.get("n_without")))

    def m(side, k):
        return ((w[side].get(k) or {}) or {}).get("mean")

    rows = []
    for k in ("min", "fga", "fta", "pts", "ast", "reb"):
        a, b = m("with", k), m("without", k)
        if a is not None and b is not None:
            rows.append((k, a, b, b - a))
    print("  %-6s %8s %8s %9s" % ("", "WITH", "WITHOUT", "delta"))
    for k, a, b, d in rows:
        print("  %-6s %8.2f %8.2f %+9.2f" % (k, a, b, d))

    fga_w = m("with", "fga") or 0
    fga_o = m("without", "fga") or 0
    fta_w = m("with", "fta") or 0
    fta_o = m("without", "fta") or 0
    mn_w = m("with", "min") or 1
    mn_o = m("without", "min") or 1
    # a free-throw trip is a scoring possession too, so FGA alone is not "usage"
    sv_w, sv_o = fga_w + 0.44 * fta_w, fga_o + 0.44 * fta_o
    print("  %-6s %8.2f %8.2f %+9.2f   <- shot volume (FGA + 0.44*FTA)" % ("shots", sv_w, sv_o, sv_o - sv_w))
    print("  %-6s %8.3f %8.3f %+9.3f   <- shot volume PER MINUTE" %
          ("/min", sv_w / mn_w, sv_o / mn_o, sv_o / mn_o - sv_w / mn_w))

    print("\n  the actual games WITHOUT %s (this is the whole sample):" % OUT_NAME)
    for g in log:
        if g["date"][:10] in out_dates:
            continue
        print("    %s  %-18s min %-5s fga %-4s fta %-4s pts %-4s ast %s"
              % (g["date"][:10], (g.get("matchup") or "")[:18], g.get("min"), g.get("fga"),
                 g.get("fta"), g.get("pts"), g.get("ast")))

print("\n" + "=" * 78)
print("=== the model's OWN bar for 'is the role really expanding?' ===")
print("  wnba_tonight line ~510: an over needs  d_min > 2  OR  d_fga > 1")
for name, pid in PEOPLE:
    w = W.wowy(W.game_log(pid), out_log)
    dmin = ((w["without"]["min"]["mean"] or 0) - (w["with"]["min"]["mean"] or 0))
    dfga = (((w["without"].get("fga") or {}).get("mean") or 0)
            - ((w["with"].get("fga") or {}).get("mean") or 0))
    print("  %-20s d_min %+5.2f (>2? %-5s)  d_fga %+5.2f (>1? %-5s)  -> %s"
          % (name, dmin, dmin > 2, dfga, dfga > 1,
             "PASSES" if (dmin > 2 or dfga > 1) else "FAILS the gate on its own merits"))
