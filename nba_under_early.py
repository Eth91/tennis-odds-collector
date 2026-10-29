#!/usr/bin/env python3
"""NBA_UNDER_PREREG.md amendment 10: the development replay of the under pings judged at tip - 30 (UNDER3050L) against
the same set judged at tip - 60 ... tip - 300 (UNDER3050L_E*), from the logged quotes and reports. Mac only, on copies
of the VM's stores. A development record, never a verdict.

    python3 nba_under_early.py --stores DIR --from 2026-10-22 --to 2026-10-28
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import nba_replay as RP
import nba_sxs_rules as SR

NAMES = ("UNDER3050L", "UNDER3050L_E60", "UNDER3050L_E120", "UNDER3050L_E180", "UNDER3050L_E240", "UNDER3050L_E300")


def moved(board, line, odds):
    """'toward' when FanDuel's close made our under dearer (a lower main line, or the same line with the under shorter),
    'away' when cheaper, 'same' when neither; None without a two-sided close."""
    m = RP.main_of(board)
    if not m or not m[2]:
        return None
    if m[0] != line:
        return "toward" if m[0] < line else "away"
    return "toward" if m[2] < odds - 1e-9 else "away" if m[2] > odds + 1e-9 else "same"


def run(stores, since, until):
    d = Path(stores)
    SR.MATCHUP_DB, SR.ROLE_GAMELOGS_DB = d / "nba_matchup.sqlite", d / "nba_gamelogs.sqlite"
    SR.TRACKING_DB, SR.LINEUPS_DB, SR.NEWS_DB = d / "nba_tracking.sqlite", d / "nba_lineups.sqlite", d / "nba_news.sqlite"
    rules = [getattr(SR, n)() for n in NAMES]
    history = RP.History(d / "nba_gamelogs.sqlite", d / "nba_matchup.sqlite")
    out = []
    for date in RP.dates(d / "nba_matchup.sqlite", d / "nba_lines.sqlite", since, until):
        day = RP.Day(date, d / "nba_lines.sqlite", d / "nba_news.sqlite", d / "nba_matchup.sqlite", history)
        sig = RP.run_day(day, rules)
        for s in sig:
            s["date"] = date
        RP.grade(day, sig, RP.box_of(d / "nba_matchup.sqlite", list(day.games)))
        cl = RP.closes(day)
        for s in sig:
            s["moved"] = moved(cl.get((s["gid"], s["pid"], s["market"])), s["line"], s["odds"])
            s["tip"] = day.games[s["gid"]]["tip"]
        out += sig
        print(f"{date}: {len(day.games)} games, " + ", ".join(f"{n} {sum(s['rule'] == n for s in sig)}" for n in NAMES), flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stores", required=True)
    ap.add_argument("--from", dest="since", required=True)
    ap.add_argument("--to", dest="until", required=True)
    ap.add_argument("--json")
    a = ap.parse_args()
    sig = run(a.stores, a.since, a.until)
    base = {(s["gid"], s["pid"], s["market"]) for s in sig if s["rule"] == "UNDER3050L"}
    res = {}
    print("\nrule              flags  also at tip-30  toward/same/away by close  CLV (95%)                 W-L   ROI")
    for n in NAMES:
        mine = [s for s in sig if s["rule"] == n]
        keys = {(s["gid"], s["pid"], s["market"]) for s in mine}
        sm = RP.summarize(mine)
        mv = {k: sum(s["moved"] == k for s in mine) for k in ("toward", "same", "away")}
        res[n] = dict(sm, moved=mv, overlap=len(keys & base), only_here=len(keys - base), missed=len(base - keys))
        c, r = sm.get("clv"), sm.get("roi")
        print(f"{n:17s} {len(mine):5d}  {len(keys & base):5d} ({len(base - keys)} of tip-30's not here)  "
              f"{mv['toward']:3d}/{mv['same']:3d}/{mv['away']:3d}            "
              + (f"{c['mean']:+.3f} [{c['lo']:+.3f},{c['hi']:+.3f}] n {c['n']}" if c else "n/a".ljust(26))
              + (f"  {r['w']}-{r['l']}  {r['mean']:+.3f}" if r else ""))
    res["note"] = "a development record (replayed), never a verdict: verdicts count only signals after registration"
    if a.json:
        Path(a.json).write_text(json.dumps({"summary": res, "signals": sig}, indent=1, default=str))


if __name__ == "__main__":
    main()
