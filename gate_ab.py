"""Gate on the ABSOLUTE with-peer rate instead of the gap. A/B, reconstructed as-of.

THE CURRENT RULE (peer_gate.peer_stat_gate) suppresses only when ALL of:
    peer plays tonight · MIN_WITH=5 / MIN_WITHOUT=3 support · with_rate < breakeven · gap >= 0.20

The Allemand case tripped three of four and survived on the gap alone: 42.9% with Rice against a
55.6% breakeven is a losing bet, but she is ALSO below breakeven without Rice (53.3%), so the GAP
is only 0.10. The gate asks "does this peer make a big difference", when what costs money is
"does this bet lose in tonight's lineup". A uniformly mediocre player is currently HARDER to gate
than a streaky one, which is backwards.

CHALLENGER: drop the gap requirement, keep everything else. Gate whenever the with-peer rate loses
at the offered price with real support.

Reported as record / units / ROI on the post-selection universe. Two things decide it, and the
second is the one that usually kills a filter:
  1. do the newly-gated bets actually lose?          (is the signal real)
  2. how many GOOD bets does it also eat?            (is the cure worse)
A filter that gates 3 losers and 8 winners is worse than no filter, however good its logic sounds.
"""
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, ".")
import peer_gate as PG
import wnba_wowy as W

STAT_VAL = {
    "points": lambda g: g.get("pts") or 0,
    "rebounds": lambda g: g.get("reb") or 0,
    "assists": lambda g: g.get("ast") or 0,
    "pts_reb": lambda g: (g.get("pts") or 0) + (g.get("reb") or 0),
    "pts_ast": lambda g: (g.get("pts") or 0) + (g.get("ast") or 0),
    "reb_ast": lambda g: (g.get("reb") or 0) + (g.get("ast") or 0),
    "pra": lambda g: (g.get("pts") or 0) + (g.get("reb") or 0) + (g.get("ast") or 0),
}


def main():
    c = sqlite3.connect("wnba_ledger.sqlite")
    cols = [d[1] for d in c.execute("PRAGMA table_info(predictions)")]
    rows = [dict(zip(cols, r)) for r in c.execute("SELECT * FROM predictions WHERE graded=1")]
    c.close()
    rows = [r for r in rows if r.get("result") in ("over", "under") and r.get("odds")]
    overs = [r for r in rows if str(r.get("side")) == "over"]
    import wnba_slip as S
    sel, _ = S.current_selection(overs, commit=False)
    uni = [r for r in sel if str(r.get("confidence")) in ("confirmed", "likely")]
    print("universe: %d graded selected {confirmed,likely} overs\n" % len(uni))

    ps = W.players()
    by_team = defaultdict(list)
    for n, d in ps.items():
        if d.get("team"):
            by_team[d["team"]].append(n)
    cache = {}

    def glog(n):
        if n not in cache:
            try:
                cache[n] = W.game_log(ps[n]["id"])
            except Exception:                                     # noqa: BLE001
                cache[n] = []
        return cache[n]

    tagged = []
    for r in uni:
        bene, team, D = r.get("player"), r.get("team"), str(r.get("pred_date"))[:10]
        outs = [o.strip() for o in str(r.get("out_player") or "").split(",") if o.strip()]
        valfn = STAT_VAL.get(r.get("stat"))
        if not bene or bene not in ps or not valfn:
            tagged.append((r, None, None))
            continue
        line, dec = float(r["line"]), float(r["odds"])
        be = 1.0 / dec
        gid = next((g["game_id"] for g in glog(bene) if str(g.get("date"))[:10] == D), None)
        blog = [g for g in glog(bene) if str(g.get("date"))[:10] < D and (g.get("min") or 0) > 0]
        worst_abs, worst_cur = None, None
        for m in by_team.get(team, []):
            if m == bene or m in outs:
                continue
            ml = glog(m)
            if not any(g["game_id"] == gid and (g.get("min") or 0) > 0 for g in ml):
                continue                                          # peer didn't play -> not the case
            mpg = ([g["min"] for g in ml if (g.get("min") or 0) > 0] or [0])
            if sum(mpg) / len(mpg) < PG.PEER_MIN_MPG:
                continue                                          # deep bench can't cannibalise
            pg = {g["game_id"] for g in ml if (g.get("min") or 0) > 0}
            wi = [g for g in blog if g["game_id"] in pg]
            wo = [g for g in blog if g["game_id"] not in pg]
            if len(wi) < PG.MIN_WITH or len(wo) < PG.MIN_WITHOUT:
                continue
            rw = sum(1 for g in wi if valfn(g) > line) / len(wi)
            ro = sum(1 for g in wo if valfn(g) > line) / len(wo)
            if rw >= be:
                continue                                          # doesn't lose with the peer
            cand = (m, rw, ro, ro - rw, be)
            if worst_abs is None or rw < worst_abs[1]:
                worst_abs = cand
            if (ro - rw) >= PG.MIN_GAP and (worst_cur is None or (ro - rw) > worst_cur[3]):
                worst_cur = cand
        tagged.append((r, worst_cur, worst_abs))

    def sc(b, lab):
        if not b:
            print("  %-30s (none)" % lab)
            return
        w = sum(1 for r in b if r["result"] == r["side"])
        u = sum((float(r["odds"]) - 1.0) if r["result"] == r["side"] else -1.0 for r in b)
        print("  %-30s %2d-%-2d  hit %5.1f%%  units %+6.2f  ROI %+6.1f%%"
              % (lab, w, len(b) - w, 100.0 * w / len(b), u, 100.0 * u / len(b)))

    cur_g = [r for r, cu, ab in tagged if cu]
    cur_k = [r for r, cu, ab in tagged if not cu]
    abs_g = [r for r, cu, ab in tagged if ab]
    abs_k = [r for r, cu, ab in tagged if not ab]
    new_g = [r for r, cu, ab in tagged if ab and not cu]          # what the change would ADD

    print("=== CURRENT rule (with_rate < breakeven AND gap >= 0.20) ===")
    sc(cur_g, "  GATED (suppressed)")
    sc(cur_k, "  kept (the board)")
    print("\n=== CHALLENGER (with_rate < breakeven, no gap requirement) ===")
    sc(abs_g, "  GATED (suppressed)")
    sc(abs_k, "  kept (the board)")
    print("\n=== THE ONLY THING THAT MATTERS: the bets the change newly kills ===")
    sc(new_g, "  newly gated")
    print("  (if these were profitable, the change costs money however sound it sounds)")
    for r, cu, ab in tagged:
        if ab and not cu:
            print("     %s %-20s %-8s o%-5s %s  peer=%-18s with %.0f%% vs BE %.0f%%, gap %.2f"
                  % (str(r["pred_date"])[:10], r["player"], r["stat"], r["line"],
                     "WON " if r["result"] == r["side"] else "LOST", ab[0],
                     100 * ab[1], 100 * ab[4], ab[3]))


if __name__ == "__main__":
    main()
