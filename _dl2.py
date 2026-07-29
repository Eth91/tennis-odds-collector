"""Per-rung pricing for DiLeo, replicating prop_edges' arithmetic exactly, to find which
gate zeroed her out."""
import statistics as st

import wnba_tonight as T
import wnba_wowy as W

pl = W.players()
who = "Megan DiLeo"
blog = W.game_log(pl[who]["id"])
barker = W.game_log(pl["Sarah Ashlee Barker"]["id"])
out_logs = [barker]
out_dm = [{g["date"][:10]: g.get("min", 0) for g in barker}]
proj = 27.0

floor = max(proj - 4, T.ROLE_FLOOR)
elev = [g for g in blog if g["min"] >= floor]
if len(elev) >= 4:
    sample, basis, k, cap = elev, "elevated", 11, 1.35
else:
    sample, basis, k, cap = [g for g in blog if g["min"] >= 12], "projected", 14, 2.2
print("proj_min %.1f | floor %.1f | basis=%s | n=%d | shrink_k=%d"
      % (proj, floor, basis, len(sample), k))
print("sample games (pts @ min -> scaled):")
vals = []
for g in sorted(sample, key=lambda x: x["date"], reverse=True):
    sc = g["pts"] * min(proj / max(g["min"], 1.0), cap)
    vals.append(sc)
    print("   %s  %2d pts @ %4.1f min  -> %5.2f" % (g["date"][:10], g["pts"], g["min"], sc))
elev_avg = st.mean(vals)
print("elev_avg = %.2f" % elev_avg)

pp = T.posted_props(who) or {}
play_prob = T._play_prob(blog, out_dm, proj)
print("\nplay_prob (role realisation) = %.3f   [gate %.2f -> %s]" % (
    play_prob, T.PLAY_PROB_GATE,
    "DISCOUNT APPLIED" if play_prob < T.PLAY_PROB_GATE else "no discount"))
print("OVER_EV_MIN = %.2f" % T.OVER_EV_MIN)
print("strict _main_line = %s | alt anchor = %s"
      % (T._main_line(pp.get("points") or {}), T._main_line(pp.get("points") or {}, allow_alt=True)))

print()
print("=" * 78)
print("POINTS rungs")
print("=" * 78)
for ln, (o, u) in sorted((pp.get("points") or {}).items()):
    if not o:
        continue
    side = "over" if elev_avg >= ln else "under"
    hit = (sum(1 for v in vals if v > ln) if side == "over"
           else sum(1 for v in vals if v < ln)) / len(vals)
    hit_raw = hit
    if side == "over" and play_prob < T.PLAY_PROB_GATE:
        hit *= play_prob
    skip = ""
    if hit >= 0.92 and o >= 2.0:
        skip = "  <-- SKIPPED (near-certain at plus money = mis-scrape guard)"
    p_adj = (hit * len(vals) + (1 / o) * k) / (len(vals) + k)
    ev = p_adj * o - 1
    mid = (st.mean(g["pts"] for g in blog) + elev_avg) / 2
    stale = abs(elev_avg - st.mean(g["pts"] for g in blog)) >= 1.0 and ln <= mid
    mark = ""
    if side == "over" and ev >= T.OVER_EV_MIN and not skip:
        mark = "  ==> +EV OVER%s" % ("  [stale]" if stale else "  [not stale -> n1 drops it]")
    print("  o%-5g @%-7.3f  %-5s raw-hit %3.0f%%  after-play-prob %3.0f%%  shrunk %3.0f%%  "
          "EV %+7.1f%%%s%s" % (ln, o, side, hit_raw * 100, hit * 100, p_adj * 100,
                               ev * 100, skip, mark))
