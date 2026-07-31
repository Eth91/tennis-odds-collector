"""Did the PEER GATE suppress DiLeo? That is the last gate between her edge and the ledger.

If it did, the model is RIGHT and the story is not "the better play was ignored" but "the better
play's sample was borrowed from a lineup that isn't happening tonight". DiLeo is a C on a roster
with two other centres, and her big without-Barker games could have been games where a centre was
also out. Run the real gate and let it answer.
"""
import wnba_alert as WA
import wnba_tonight as T
import wnba_wowy as W

try:
    import wnba_peer_gate as _PG
except ImportError:
    _PG = WA._PG

print("  _PEER_GATED:", getattr(WA, "_PEER_GATED", "(not found)"))

OUT_PID, OUT_NAME = 4703794, "Sarah Ashlee Barker"
pl = W.players()
out_log = W.game_log(OUT_PID)

for name, line, dec, proj in (("Megan DiLeo", 14.5, 2.04, 27.0),
                              ("Bridget Carleton", 14.5, 2.68, 31.0),
                              ("Bridget Carleton", 12.5, 1.9804, 31.0)):
    v = pl.get(name)
    if not v:
        print("  %s not on roster" % name)
        continue
    blog = W.game_log(v["id"])
    team = v["team"]
    tlogs = {x: W.game_log(vv["id"]) for x, vv in pl.items()
             if vv.get("team") == team and x != name and (vv.get("gp") or 0) >= 5}
    print("\n=== %s  %s o%g @ %s  (pos %s, team %s) ===" % (name, "points", line, dec,
                                                            v.get("position"), team))
    print("    teammates considered: %d" % len(tlogs))
    try:
        hit = _PG.peer_stat_gate(
            blog, getattr(WA, "_PEER_GATED", {}).get("points", None), line, dec, tlogs,
            lambda x: True,                       # assume every non-out teammate plays tonight
            exclude=[OUT_NAME], proj_min=proj,
            mpg_of=lambda x: (pl.get(x) or {}).get("min"))
    except Exception as e:
        print("    peer_stat_gate raised: %r" % (e,))
        continue
    if hit:
        print("    SUPPRESSED by peer gate:")
        print("      peer          %s" % hit.get("peer"))
        print("      rate WITH peer    %.0f%%" % (100 * (hit.get("rate_with") or 0)))
        print("      rate WITHOUT peer %.0f%%" % (100 * (hit.get("rate_without") or 0)))
        print("      breakeven         %.0f%%" % (100 * (hit.get("breakeven") or 0)))
        print("      -> her over is priced off games this peer MISSED; the peer plays tonight.")
    else:
        print("    peer gate: NOT suppressed")

print("\n=== POR centres and their availability ===")
for nm, d in sorted(pl.items()):
    if d.get("team") == "POR" and d.get("position") in ("C", "F"):
        print("  %-24s %-3s gp=%-3s min=%.1f" % (nm, d.get("position"), d.get("gp"), d.get("min") or 0))
