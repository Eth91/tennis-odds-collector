"""Why is Megan DiLeo no longer producing an n1 flag? Walk every gate in order."""
import statistics as st

import wnba_context as CTX
import wnba_tonight as T
import wnba_wowy as W
from wnba_alert import position_compat, N1_PILOT

pl = W.players()
inj = T.injuries()
mus = T.tonight_matchups()
team = "POR"

print("=" * 74)
print("POR injury view")
print("=" * 74)
for n, s in inj.items():
    v = pl.get(n) or {}
    if v.get("team") == team:
        print("  %-24s %-12s %.1f mpg %.1f ppg  impact=%s" % (
            n, s, v.get("min", 0), v.get("pts", 0),
            v.get("min", 0) >= 20 or v.get("pts", 0) >= 10))

OUTS = [n for n, s in inj.items()
        if (pl.get(n) or {}).get("team") == team and s in ("Out", "Doubtful")
        and ((pl.get(n) or {}).get("min", 0) >= 20 or (pl.get(n) or {}).get("pts", 0) >= 10)]
print("\nimpact outs:", OUTS)
if not OUTS:
    raise SystemExit("no impact out -> no POR cascade at all")

outs = [(n, pl[n]) for n in OUTS]
out_logs = [W.game_log(p["id"]) for _, p in outs]
out_dm = [{g["date"][:10]: g.get("min", 0) for g in ol} for ol in out_logs]
vacated = {"points": sum(p["pts"] for _, p in outs),
           "rebounds": sum(p["reb"] for _, p in outs),
           "assists": sum(p["ast"] for _, p in outs)}
ctx = CTX.matchup_context(team, mus.get(team, ""), CTX.game_lines(), CTX.team_rates())

who = "Megan DiLeo"
v = pl[who]
blog = W.game_log(v["id"])
w = W.wowy_multi(blog, out_logs)
if w["n_without"] < 2 and len(outs) > 1:
    cands = [(W.wowy(blog, ol), nm) for (nm, _), ol in zip(outs, out_logs)]
    w = max(cands, key=lambda x: x[0]["n_without"])[0]

print()
print("=" * 74)
print("GATE WALK — %s" % who)
print("=" * 74)
nw = w["n_without"]
with_min = w["with"]["min"]["mean"]
wo_min = w["without"]["min"]["mean"]
print("  1. n_without .................. %d   %s" % (
    nw, "n1 TIER" if nw == 1 else ("firm tier" if nw >= 2 else "cold-start")))
print("     N1_PILOT flag .............. %s" % N1_PILOT)
pw = position_compat(v.get("position"), [op.get("position") for _, op in outs])
proj = with_min + pw * (wo_min - with_min)
r5 = [g["min"] for g in blog[:5] if g["min"] > 8]
if r5:
    proj = max(proj, st.median(r5))
print("  2. minutes: with %.1f -> without %.1f  (bump %+.1f, needs >= 3.0 for n1)  %s" % (
    with_min, wo_min, wo_min - with_min, "PASS" if (wo_min - with_min) >= 3.0 else "FAIL"))
print("     pos-fit %.2f  ->  proj_min %.1f" % (pw, proj))

posted = T.posted_props(who) or {}
print("  3. posted markets ............. %s" % (sorted(posted) or "NONE"))
for stat, best in sorted(posted.items()):
    print("       %-9s rungs %s" % (stat, sorted((l, o) for l, (o, u) in best.items())))

edges = T.prop_edges(who, blog, proj, w, vacated, ctx, out_logs=out_dm,
                     opp=mus.get(team, ""), pos=v.get("position"))
print("  4. prop_edges returned %d spot(s)" % len(edges))
for e in edges:
    print("       %-9s o%-5g @%-6.2f ev %+6.1f%%  side=%-5s stale=%s" % (
        e["stat"], e["line"], e["dec"], e["ev"] * 100, e["side"], e.get("stale")))
overs_stale = [e for e in edges if e["side"] == "over" and e["stale"]]
print("  5. n1 keeps only over AND stale -> %d spot(s)  %s" % (
    len(overs_stale), "FLAG" if overs_stale else "NO FLAG"))

# show the stale arithmetic explicitly for points
print()
print("=" * 74)
print("THE 'stale' TEST, spelled out (points)")
print("=" * 74)
floor = max(proj - 4, T.ROLE_FLOOR)
elev = [g for g in blog if g["min"] >= floor]
sample = elev if len(elev) >= 4 else [g for g in blog if g["min"] >= 12]
cap = 1.35 if len(elev) >= 4 else 2.2
vals = [g["pts"] * min(proj / max(g["min"], 1.0), cap) for g in sample]
season_avg = st.mean(g["pts"] for g in blog) if blog else 0
elev_avg = st.mean(vals) if vals else 0
mid = (season_avg + elev_avg) / 2
print("  season_avg %.2f | elev_avg %.2f | midpoint %.2f" % (season_avg, elev_avg, mid))
print("  gap |elev-season| = %.2f  (needs >= 1.0)  %s" % (
    abs(elev_avg - season_avg), "ok" if abs(elev_avg - season_avg) >= 1.0 else "FAILS"))
pp = posted.get("points") or {}
for ln in sorted(pp):
    print("     line %-5g <= mid %.2f ? %-5s -> stale=%s" % (
        ln, mid, ln <= mid, abs(elev_avg - season_avg) >= 1.0 and ln <= mid))
print()
print("  her last 6 games (pts / min):")
for g in sorted(blog, key=lambda x: x["date"], reverse=True)[:6]:
    print("     %s  %2d pts  %4.1f min" % (g["date"][:10], g["pts"], g["min"]))
