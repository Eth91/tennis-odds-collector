"""Call the REAL prop_edges for Carleton and DiLeo and print every edge plus the gate arithmetic.

Established so far: both have n_without=2 off the same out player, DiLeo's 2-game split is strongly
positive (+4.2 min, +6.1 pts) and Carleton's is negative (+0.3 min, -1.3 pts) — yet Carleton got the
firm bet and DiLeo got nothing. The remaining question is which gate produced that inversion, and
guessing from source is not good enough, so this runs the function itself.
"""
import json

import wnba_tonight as T
import wnba_wowy as W

OUT_PID = 4703794                      # Sarah Ashlee Barker
PEOPLE = (("Bridget Carleton", 3906972, 31.0, "F"),
          ("Megan DiLeo", 3934218, 27.0, "C"))

out_log = W.game_log(OUT_PID)
out_dm = {g["date"][:10]: g["min"] for g in out_log}      # loop passes out_logs as [{date: min}]

print("=== gate constants as deployed ===")
for k in ("OVER_EV_MIN", "ROLE_GUARD_MINN", "THIN_SAMPLE_N", "BIG_JUMP_MIN",
          "COLD_START_MARGIN", "PLAY_PROB_GATE", "VOL_LIVE", "EV_CAP", "MIN_ELEV_N"):
    if hasattr(T, k):
        print("  T.%-18s = %r" % (k, getattr(T, k)))

for name, pid, pmin, pos in PEOPLE:
    log = W.game_log(pid)
    w = W.wowy(log, out_log)
    print("\n" + "=" * 74)
    print("=== %s   proj_min=%s  pos=%s  n_without=%s" % (name, pmin, pos, w.get("n_without")))
    dmin = ((w["without"]["min"]["mean"] or 0) - (w["with"]["min"]["mean"] or 0))
    dfga = ((w["without"].get("fga") or {}).get("mean") or 0) - \
           ((w["with"].get("fga") or {}).get("mean") or 0)
    print("    WOWY d_min=%+.2f  d_fga=%+.2f" % (dmin, dfga))
    print("    CONVICTION GATE (over needs d_min>2 OR d_fga>1): d_min>2=%s  d_fga>1=%s  -> %s"
          % (dmin > 2, dfga > 1,
             "PASS" if (dmin > 2 or dfga > 1) else "SKIP (unless use_vol exempts it)"))
    print("    BAND SHADOW (d_min<0 or >8): %s" % (dmin < 0 or dmin > 8))
    try:
        edges = list(T.prop_edges(name, log, pmin, w=w, vacated=None, ctx=None,
                                  out_logs=[out_dm], opp="IND", pos=pos))
    except Exception as e:
        print("    prop_edges raised: %r" % (e,))
        continue
    if not edges:
        print("    prop_edges -> NO EDGES AT ALL")
        continue
    print("    prop_edges -> %d edge(s)" % len(edges))
    for e in sorted(edges, key=lambda x: -(x.get("ev") or 0)):
        print("      %-9s o%-6g dec=%-7s ev=%+.3f hit=%-6s n=%-3s basis=%-9s "
              "d_min=%-6s d_stat=%-6s band=%s vol=%s"
              % (e.get("stat"), e.get("line"), e.get("dec"), e.get("ev") or 0,
                 e.get("hit"), e.get("n"), e.get("basis"), e.get("d_min"),
                 e.get("d_stat"), e.get("band_pilot"), e.get("use_vol")))
        if e.get("stat") == "points":
            print("           season_avg=%s elev_avg=%s  (elev_avg is the ELEVATED-MINUTES sample, "
                  "NOT the without-star sample)" % (e.get("season_avg"), e.get("elev_avg")))

print("\n=== so which sample is the bet actually standing on? ===")
print("  d_stat  = WOWY delta        -> the injury-specific claim (n_without=2 here)")
print("  elev_avg= elevated-minutes  -> games where the player already had a big role, for ANY reason")
print("  If elev_avg carries the over while d_stat is negative, the 'beneficiary' framing is")
print("  decoration: nothing about THIS injury is driving the number.")
