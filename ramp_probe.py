"""RETURNING-PEER RAMP: the signal peer_regime cannot see, because it asks a binary question.

peer_regime asks "did the peer PLAY?" — a yes/no. That is the right question when a peer's role is
stable, and the wrong one when the peer is on their way back from an absence, because a returning
player's minutes are a MOVING TARGET.

The Allemand case is the clean example. Her elevated sample has 11 games; only 2 match tonight's
lineup (Rice playing), so peer_regime correctly flags 6.0 borrowed minutes. But BOTH matching games
are themselves ramp games — Rice at 17 and 23 minutes against a 26.7-minute pre-absence norm. So
the matched sub-sample, the one peer_regime says to trust, is ALSO built from a lineup that is not
tonight's: it is built from a Rice who was still working back. Tonight is her third game, she has
climbed 17 -> 23, and the game where she got closest to her norm is the game Allemand fell to 22
minutes. Every version of the comparison points the same way and the model sees none of it.

WHAT THIS MEASURES, per returning peer:
    games_missed   how long they were out (a 1-game rest is not a ramp)
    games_back     how many since returning (the ramp window)
    trend          minutes change across those games
    deficit        how far below their own pre-absence norm they still are
A peer is RAMPING when they missed enough to lose their role, are early enough back to still be
regaining it, and are still below their own baseline. The deficit is the headroom the beneficiary
is about to give back.

This probe answers two questions before anything is wired anywhere:
  1. how OFTEN does a ramping peer sit behind a flagged bet? (rare = not worth modelling)
  2. do those bets do worse? (measured on the post-selection universe, in units, never MAE)
"""
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, ".")
import wnba_wowy as W

MISSED_MIN = 3          # fewer than 3 missed games is a rest, not a role loss
BACK_MAX = 4            # after ~4 games the role is re-established; no longer a ramp
DEFICIT_MIN = 2.0       # still this far under their own norm


def ramp_state(peer_log, as_of):
    """None, or the ramp state of `peer` as of date `as_of` (strictly-prior games only)."""
    gs = sorted([g for g in peer_log if str(g.get("date"))[:10] < as_of],
                key=lambda g: str(g.get("date"))[:10])
    played = [g for g in gs if (g.get("min") or 0) > 0]
    if len(played) < 4:
        return None
    # walk back from the most recent game to find the last absence block
    last_dates = [str(g.get("date"))[:10] for g in played]
    # a "miss" is a team game the player did not appear in; approximate with date gaps in their
    # own log, which is what is available without a team schedule join.
    back = []
    for g in reversed(played):
        back.append(g)
        if len(back) > BACK_MAX:
            break
    games_back = len(back)
    # crude absence detector: a >=12 day hole before the current stretch
    import datetime as dt
    def d(x):
        return dt.date.fromisoformat(str(x.get("date"))[:10])
    gap_days = None
    if len(played) >= games_back + 1:
        gap_days = (d(back[-1]) - d(played[-(games_back + 1)])).days
    if gap_days is None or gap_days < 12:
        return None                                   # no real absence -> no ramp
    pre = [g for g in played[:-games_back]][-8:]
    if len(pre) < 3:
        return None
    norm = sum(g["min"] for g in pre) / len(pre)
    cur = list(reversed(back))                        # chronological, since return
    if len(cur) > BACK_MAX:
        cur = cur[:BACK_MAX]
    mins = [g["min"] for g in cur]
    deficit = norm - (sum(mins) / len(mins))
    if len(cur) > BACK_MAX or deficit < DEFICIT_MIN:
        return None
    return {"games_back": len(cur), "gap_days": gap_days, "norm": round(norm, 1),
            "since": mins, "deficit": round(deficit, 1),
            "trend": round(mins[-1] - mins[0], 1) if len(mins) > 1 else 0.0}


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
    print("universe: %d" % len(uni))

    ps = W.players()
    by_team = defaultdict(list)
    for n, dd in ps.items():
        if dd.get("team"):
            by_team[dd["team"]].append(n)
    cache = {}

    def glog(n):
        if n not in cache:
            try:
                cache[n] = W.game_log(ps[n]["id"])
            except Exception:                                    # noqa: BLE001
                cache[n] = []
        return cache[n]

    ramped, plain = [], []
    for r in uni:
        bene, team, D = r.get("player"), r.get("team"), str(r.get("pred_date"))[:10]
        outs = [o.strip() for o in str(r.get("out_player") or "").split(",") if o.strip()]
        if not bene or bene not in ps:
            continue
        gid = next((g["game_id"] for g in glog(bene) if str(g.get("date"))[:10] == D), None)
        hit = None
        for m in by_team.get(team, []):
            if m == bene or m in outs:
                continue
            ml = glog(m)
            if not any(g["game_id"] == gid and (g.get("min") or 0) > 0 for g in ml):
                continue                                          # peer didn't play -> not tonight
            st = ramp_state(ml, D)
            if st and (hit is None or st["deficit"] > hit[1]["deficit"]):
                hit = (m, st)
        (ramped if hit else plain).append((r, hit))

    def score(b, lab):
        if not b:
            print("  %-26s (empty)" % lab); return
        w = sum(1 for r, _ in b if r["result"] == r["side"])
        u = sum((float(r["odds"]) - 1.0) if r["result"] == r["side"] else -1.0 for r, _ in b)
        print("  %-26s %2d-%-2d  hit %5.1f%%  units %+6.2f  ROI %+6.1f%%"
              % (lab, w, len(b) - w, 100.0 * w / len(b), u, 100.0 * u / len(b)))

    print("\n=== 1. how often is a RAMPING peer behind a flagged bet? ===")
    print("  %d of %d (%.0f%%)" % (len(ramped), len(uni), 100.0 * len(ramped) / max(len(uni), 1)))
    print("\n=== 2. do those bets do worse? ===")
    score(plain, "no ramping peer")
    score(ramped, "RAMPING PEER")
    for r, h in sorted(ramped, key=lambda x: -x[1][1]["deficit"])[:8]:
        print("    %s %-20s %-8s %-5s %s peer=%-18s back=%d def=%.1f since=%s"
              % (str(r["pred_date"])[:10], r["player"], r["stat"], r["line"],
                 "WON " if r["result"] == r["side"] else "LOST",
                 h[0], h[1]["games_back"], h[1]["deficit"], h[1]["since"]))


if __name__ == "__main__":
    main()
