"""(a) What fires for SEA if Malonga is ruled out?
   (b) Would Rivers pts o6.5 @1.77 have been flagged, had the bot seen the market?
"""
import statistics as st

import wnba_context as CTX
import wnba_tonight as T
import wnba_wowy as W
from wnba_alert import position_compat, COMBO_PRICED_N

pl = W.players()
inj = T.injuries()
mus = T.tonight_matchups()
lines_v, rates = CTX.game_lines(), CTX.team_rates()

# ---------------------------------------------------------------- (a) SEA / Malonga
print("=" * 76)
print("(a) SEA CASCADE IF MALONGA IS RULED OUT")
print("=" * 76)
sea_inj = {n: s for n, s in inj.items() if (pl.get(n) or {}).get("team") == "SEA"}
print("  SEA injury view now:", sea_inj)
for n in sea_inj:
    v = pl.get(n) or {}
    print("     %-22s %.1f mpg %.1f ppg  impact=%s" % (
        n, v.get("min", 0), v.get("pts", 0), v.get("min", 0) >= 20 or v.get("pts", 0) >= 10))

OUTS = [n for n, s in sea_inj.items() if s in ("Out", "Doubtful")] + ["Dominique Malonga"]
OUTS = [n for n in dict.fromkeys(OUTS)
        if (pl.get(n) or {}).get("min", 0) >= 20 or (pl.get(n) or {}).get("pts", 0) >= 10]
print("\n  impact outs in the counterfactual:", OUTS)
if not OUTS:
    print("  -> no impact out; no cascade forms even with Malonga out")
else:
    outs = [(n, pl[n]) for n in OUTS]
    out_logs = [W.game_log(p["id"]) for _, p in outs]
    out_dm = [{g["date"][:10]: g.get("min", 0) for g in ol} for ol in out_logs]
    vacated = {"points": sum(p["pts"] for _, p in outs),
               "rebounds": sum(p["reb"] for _, p in outs),
               "assists": sum(p["ast"] for _, p in outs)}
    ctx = CTX.matchup_context("SEA", mus.get("SEA", ""), lines_v, rates)
    print("  vacated pool: %.1f pts / %.1f reb / %.1f ast" % (
        vacated["points"], vacated["rebounds"], vacated["assists"]))
    # combination novelty (the new gate)
    tdates = set()
    for n, v in pl.items():
        if v.get("team") == "SEA":
            for g in W.game_log(v["id"]) or []:
                tdates.add(g["date"][:10])
    absent = [{g["date"][:10] for g in ol if (g.get("min") or 0) > 0} for ol in out_logs]
    n_combo = sum(1 for d in tdates if d < "2026-07-28" and all(d not in a for a in absent))
    print("  prior games with this exact set out: %d (priced at >=%d)" % (n_combo, COMBO_PRICED_N))
    print()
    team_pl = {n: v for n, v in pl.items()
               if v["team"] == "SEA" and n not in set(OUTS) and v["gp"] >= 5}
    for n, v in sorted(team_pl.items(), key=lambda x: -x[1]["min"]):
        blog = W.game_log(v["id"])
        if not blog:
            continue
        w = W.wowy_multi(blog, out_logs)
        if w["n_without"] < 2 and len(outs) > 1:
            cands = [(W.wowy(blog, ol), nm) for (nm, _), ol in zip(outs, out_logs)]
            w = max(cands, key=lambda x: x[0]["n_without"])[0]
        if w["n_without"] < 2:
            print("  %-24s n_without=%d (too thin)" % (n, w["n_without"]))
            continue
        pw = position_compat(v.get("position"), [op.get("position") for _, op in outs])
        with_min = w["with"]["min"]["mean"]
        proj = with_min + pw * (w["without"]["min"]["mean"] - with_min)
        r5 = [g["min"] for g in blog[:5] if g["min"] > 8]
        if r5:
            proj = max(proj, st.median(r5))
        if proj - with_min <= 0.3 and pw < 0.6:
            print("  %-24s no minutes bump (%.1f->%.1f) pos-fit %.2f -> dropped"
                  % (n, with_min, proj, pw))
            continue
        edges = T.prop_edges(n, blog, proj, w, vacated, ctx, out_logs=out_dm,
                             opp=mus.get("SEA", ""), pos=v.get("position"))
        posted = T.posted_props(n) or {}
        if not posted:
            print("  %-24s proj %.1f d_min %+.1f  NO FD MARKET" % (
                n, proj, w["without"]["min"]["mean"] - with_min))
            continue
        print("  %-24s proj %.1f d_min %+.1f n=%d -> %d edge(s)" % (
            n, proj, w["without"]["min"]["mean"] - with_min, w["n_without"], len(edges)))
        for e in sorted(edges, key=lambda x: -x["ev"]):
            print("       %-9s o%-5g @%-6.2f ev %+6.1f%% hit %.0f%% proj %.1f%s"
                  % (e["stat"], e["line"], e["dec"], e["ev"] * 100, e["hit"] * 100,
                     e["elev_avg"], "  [stale]" if e.get("stale") else ""))

# ---------------------------------------------------------------- (b) Rivers o6.5
print()
print("=" * 76)
print("(b) WOULD RIVERS pts o6.5 @1.77 HAVE BEEN FLAGGED?")
print("=" * 76)
v = pl["Saniya Rivers"]
blog = W.game_log(v["id"])
outs_con = [(n, pl[n]) for n in ("Brittney Griner", "Aaliyah Edwards") if n in pl]
out_logs_c = [W.game_log(p["id"]) for _, p in outs_con]
w = W.wowy_multi(blog, out_logs_c)
if w["n_without"] < 2:
    cands = [(W.wowy(blog, ol), nm) for (nm, _), ol in zip(outs_con, out_logs_c)]
    w = max(cands, key=lambda x: x[0]["n_without"])[0]
pw = position_compat(v.get("position"), [op.get("position") for _, op in outs_con])
with_min = w["with"]["min"]["mean"]
proj_min = with_min + pw * (w["without"]["min"]["mean"] - with_min)
r5 = [g["min"] for g in blog[:5] if g["min"] > 8]
if r5:
    proj_min = max(proj_min, st.median(r5))
floor = max(proj_min - 4, T.ROLE_FLOOR)
elev = [g for g in blog if g["min"] >= floor]
basis = "elevated" if len(elev) >= 4 else "projected(breakout)"
sample = elev if len(elev) >= 4 else [g for g in blog if g["min"] >= 12]
k = 11 if len(elev) >= 4 else 14
cap = 1.35 if len(elev) >= 4 else 2.2
vals = [g["pts"] * min(proj_min / max(g["min"], 1.0), cap) for g in sample]
print("  proj_min %.1f (role floor %.1f) | basis=%s n=%d shrink_k=%d"
      % (proj_min, floor, basis, len(vals), k))
print("  minutes-honest projection: %.2f pts" % st.mean(vals))
for line, price in ((6.5, 1.77), (4.5, 1.3226), (9.5, 3.25)):
    proj = st.mean(vals)
    side = "over" if proj >= line else "under"
    hit = sum(1 for x in vals if x > line) / len(vals)
    p_adj = (hit * len(vals) + (1 / price) * k) / (len(vals) + k)
    ev = p_adj * price - 1
    verdict = ("FLAG" if (side == "over" and ev >= T.OVER_EV_MIN) else
               "no bet (%s)" % ("under-side" if side != "over" else "EV below %.0f%%"
                                % (T.OVER_EV_MIN * 100)))
    print("     o%-5g @%-7.3f  proj %.2f -> %-5s raw-hit %3.0f%%  shrunk %3.0f%%  "
          "EV %+6.1f%%  => %s" % (line, price, proj, side, hit * 100, p_adj * 100,
                                  ev * 100, verdict))
