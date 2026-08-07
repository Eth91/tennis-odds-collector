#!/usr/bin/env python3
"""wnba_ladder_guard — name the players whose ladder is MILESTONE-ONLY.

THE FAILURE IT CATCHES (2026-08-06, Puoch). FanDuel posts "Nyadiew Puoch - Points" at
O 5.5 -106 / U 5.5 -120. That market is reachable by SEARCH but is not referenced by any
card in the event-page `player-points` tab, which returns a curated 29-market subset with
no pagination field to page past. So the collector banks only her appearances in the shared
"To Score 5+ / 10+ Points" milestone markets -> rungs [4.5, 9.5], over-only.

prop_edges then anchors on the lowest rung, 4.5 @ 1.5747 = 63.5% implied, and reports
-6.1% EV. That number is CORRECT for the rung it priced and MEANINGLESS for the bet that
exists. A data gap wearing a model verdict -- the silent-zero shape that has caused every
outage in this repo: unreadable input reported as a real value instead of refused.

WHY THIS REPORTS RATHER THAN SUPPRESSES. A milestone-only ladder is not automatically
unplayable: Monique Akoa Makani flagged twice on 2026-08-06 off exactly such a ladder
(points 7.5 +40.1% EV, 9.5 +42.1%) because her projection cleared the rung by a mile.
Killing those would trade a silent miss for a silent loss. So this NAMES the players whose
ladder is structurally incomplete and leaves pricing alone -- the operator can eyeball a
real main line the pipeline cannot see. Suppression would be the wrong guard; visibility
is the right one.

Standalone by design: touches no frozen v1.3 file (wnba_alert/slip/tonight/wowy).
"""
import sys
from collections import defaultdict

sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_tonight as T
import wnba_wowy as W

STATS = ("points", "rebounds", "assists")


def scan(players=None):
    """-> {player: {stat: [rungs]}} for stats whose ladder has NO two-sided rung."""
    pl = players if players is not None else W.players()
    bad = defaultdict(dict)
    for name in pl:
        try:
            pp = T.posted_props(name)
        except Exception:
            continue
        if not pp:
            continue
        for stat in STATS:
            ladder = pp.get(stat)
            if not ladder:
                continue
            # a rung is two-sided when BOTH prices are real; posted_props stores 0.0 for a
            # side no book offered, which is exactly how a milestone rung presents
            two_sided = [k for k, v in ladder.items()
                         if v and len(v) >= 2 and v[0] and v[1]]
            if not two_sided:
                bad[name][stat] = sorted(ladder)
    return bad


def main():
    bad = scan()
    if not bad:
        print("ladder guard: every posted ladder has a two-sided rung — clean")
        return 0
    n = sum(len(v) for v in bad.values())
    print(f"ladder guard: {len(bad)} player(s), {n} stat(s) MILESTONE-ONLY — a real main "
          f"line may exist that the collector cannot see")
    for name in sorted(bad):
        for stat, rungs in sorted(bad[name].items()):
            anchor = min(rungs) if rungs else None
            px = None
            try:
                px = T.posted_props(name)[stat][anchor][0]
            except Exception:
                pass
            imp = f"{100.0/px:.1f}% implied" if px else "?"
            print(f"   {name:<24} {stat:<9} rungs={rungs}  "
                  f"would anchor {anchor} @ {px} ({imp})")
    print("   -> these price off a milestone rung, NOT the market's main line.")
    print("   -> check them by hand; a negative EV here may be a missing line, not a pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
