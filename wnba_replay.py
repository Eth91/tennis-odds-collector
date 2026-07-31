"""Replay the ACTUAL decision for Carleton and DiLeo through the real prop_edges.

Everything so far has been inferred from stored rows. This runs the live code on both players with
the same inputs the loop uses, so the answer is what the model does, not what I think it does.

The two questions that decide whether this is a bug or correct behaviour:
  1. DiLeo's n_without. Her points went to the USG shadow, which only fires at n_without in (1,2).
     If her +4.2 d_min is a 1-2 game measurement, shadowing it is CORRECT — the n=1/n=2 points cell
     is documented as a coin flip. If n_without is large, shadowing it is a bug.
  2. Carleton passes the conviction gate at d_min=0.3 only via d_fga>1. Confirm that, and resolve
     the d_stat=-1.3 vs elev_avg 16.1 > season_avg 13.7 contradiction — if the bet leans on
     elev_avg while the WOWY says she scores LESS, the two numbers are measuring different samples
     and only one of them is the beneficiary claim.
"""
import json
import sqlite3

import wnba_tonight as T
import wnba_wowy as W

DATE = "2026-07-31"
OUT = "Sarah Ashlee Barker"
WHO = ["Bridget Carleton", "Megan DiLeo"]

# resolve ids + game logs the same way the loop does
con = sqlite3.connect("wnba_gamelogs.sqlite")
con.row_factory = sqlite3.Row


def pid_of(name):
    for t in ("players", "roster", "gamelogs"):
        try:
            r = con.execute("SELECT DISTINCT pid, player FROM %s WHERE player LIKE ? LIMIT 1" % t,
                            ("%" + name.split()[-1] + "%",)).fetchone()
            if r:
                return r["pid"]
        except sqlite3.Error:
            continue
    return None


ids = {n: pid_of(n) for n in WHO + [OUT]}
print("  ids:", ids)
glog = T.glog if hasattr(T, "glog") else None
if glog is None:
    import wnba_alert as WA
    glog = WA.glog
out_log = glog(ids[OUT]) if ids.get(OUT) else []
print("  out_player log games: %d" % len(out_log))

print("\n=== WOWY, the number that decides which engine sees the player ===")
for n in WHO:
    bl = glog(ids[n]) if ids.get(n) else []
    if not bl:
        print("  %-20s no game log" % n)
        continue
    w = W.wowy(bl, out_log)
    dmin = (w["without"]["min"]["mean"] or 0) - (w["with"]["min"]["mean"] or 0)
    def _m(side, k):
        return ((w[side].get(k) or {}) or {}).get("mean")
    print("  %-20s games=%-3d  n_WITH=%-3s n_WITHOUT=%-3s  d_min=%+.1f"
          % (n, len(bl), w["with"].get("n", "?"), w["n_without"], dmin))
    for k in ("min", "pts", "fga", "fta", "reb"):
        a, b = _m("with", k), _m("without", k)
        if a is not None and b is not None:
            print("        %-4s with %6.2f  without %6.2f   delta %+.2f" % (k, a, b, b - a))
    print("        -> engine: %s" % (
        "COLD n=0" if w["n_without"] < 1 else
        "n1 SPEED PILOT" if w["n_without"] == 1 else
        "USG SHADOW ONLY (elevated basis needs n>=3)" if w["n_without"] == 2 else
        "FIRM elevated basis"))

print("\n=== what prop_edges actually returns for each ===")
for n in WHO:
    bl = glog(ids[n]) if ids.get(n) else []
    if not bl:
        continue
    w = W.wowy(bl, out_log)
    props = T.posted_props(n)
    print("\n  --- %s  (posted props: %s)"
          % (n, list((props or {}).keys()) if props else "NONE"))
    if not props:
        print("      no FanDuel props posted -> nothing can flag")
        continue
    try:
        edges = list(T.prop_edges(n, bl, None, w, None, None, out_logs=[out_log], opp="IND"))
    except TypeError:
        edges = None
        print("      (prop_edges needs loop context; falling back to stored rows)")
    if edges is not None:
        if not edges:
            print("      prop_edges returned NOTHING -> no flag")
        for e in edges:
            print("      %-9s o%-6s dec=%-6s ev=%+.3f d_min=%s d_fga=%s band_pilot=%s"
                  % (e.get("stat"), e.get("line"), e.get("dec"), e.get("ev") or 0,
                     e.get("d_min"), e.get("d_fga"), e.get("band_pilot")))

print("\n=== the stored Carleton row: does the bet lean on elev_avg while WOWY says down? ===")
lc = sqlite3.connect("wnba_ledger.sqlite")
lc.row_factory = sqlite3.Row
for r in lc.execute("SELECT * FROM predictions WHERE pred_date=? AND player LIKE '%Carleton%'", (DATE,)):
    d = dict(r)
    print("  line=%s odds=%s ev=%s proj_hit=%s" % (d["line"], d["odds"], d["ev"], d["proj_hit"]))
    print("    season_avg=%s  elev_avg=%s  (elev - season = %+.1f)"
          % (d["season_avg"], d["elev_avg"], (d["elev_avg"] or 0) - (d["season_avg"] or 0)))
    print("    d_stat=%s  d_min=%s  d_fga=%s  d_fta=%s  d_3pa=%s"
          % (d["d_stat"], d["d_min"], d["d_fga"], d["d_fta"], d["d_3pa"]))
    print("    basis=%s n_elev=%s samples=%s" % (d["basis"], d["n_elev"], d["samples"]))
    print("    CONVICTION GATE needs d_min>2 OR d_fga>1  ->  d_min>2: %s   d_fga>1: %s"
          % ((d["d_min"] or 0) > 2, (d["d_fga"] or 0) > 1))
    print("    BAND SHADOW needs d_min<0 or >8           ->  %s (0-3 zone = stays FIRM, tier B)"
          % ((d["d_min"] or 0) < 0 or (d["d_min"] or 0) > 8))
lc.close()
con.close()
