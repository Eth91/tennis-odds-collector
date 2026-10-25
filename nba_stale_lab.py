#!/usr/bin/env python3
"""The stale-prop lab — NBA_SPEED_PREREG.md amendment 25. Information only: nothing here flags or pings.

The card fills on a few percent of flags, so its own record will take a season. The lab learns from every
prop instead: each teammate prop FanDuel had posted when an absence broke (nba_reaction's affected set,
earliest trigger per game-player-stat). Taken: the OVER at FanDuel's main line and price at the news
(T0). Graded: FanDuel's main line at tip (beat close), the box score (won, flat units, DNP void), and the
PREMISE (did the absent player actually sit?). Joined: the model's view at first sighting (flag-pass
`cands`): excess = (proj - line) / threshold.

UNIT = one ABSENCE x one prop (corrected 2026-10-25, before any decision): the earliest trigger for that
absent player, per teammate prop. Deduping per prop alone folded a later absence into an earlier trigger
for another player, which hid RotoBaller's false "Jalen Green" news under an earlier report trigger.

    python3 nba_stale_lab.py            # the registered slices
"""
from __future__ import annotations

import json
import random
import sqlite3
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "nba_lab_cache.sqlite"
SHADOW = HERE / "nba_shadow.sqlite"
LINES = HERE / "nba_lines.sqlite"
BOXKEY = {"points": ("points",), "rebounds": ("reboundsTotal",), "assists": ("assists",),
          "threes": ("threePointersMade",), "pra": ("points", "reboundsTotal", "assists"),
          "pts_reb": ("points", "reboundsTotal"), "pts_ast": ("points", "assists"),
          "reb_ast": ("reboundsTotal", "assists")}
CAND_STAT = {"pts": "points", "reb": "rebounds", "pra": "pra"}


def final_box(gid, get=None, cache=None):
    """{personId: player dict (+ '_team')} for a FINAL game, cached on disk; None until final."""
    con = sqlite3.connect(cache or CACHE)
    con.execute("CREATE TABLE IF NOT EXISTS box (gid TEXT PRIMARY KEY, js TEXT)")
    row = con.execute("SELECT js FROM box WHERE gid=?", (gid,)).fetchone()
    if row:
        con.close()
        return {int(k): v for k, v in json.loads(row[0]).items()}
    if get is None:
        import nba_rosters as R
        get = lambda g: R._get(R.BOX.format(g))["game"]
    try:
        b = get(gid)
    except Exception:                                                    # noqa: BLE001
        con.close()
        return None
    if b.get("gameStatus") != 3:
        con.close()
        return None
    players = {p["personId"]: dict(p, _team=b[s]["teamTricode"]) for s in ("homeTeam", "awayTeam")
               for p in b[s]["players"]}
    con.execute("INSERT OR REPLACE INTO box VALUES (?,?)", (gid, json.dumps(players)))
    con.commit()
    con.close()
    return players


def grade(line0, odds0, close, actual):
    """(beat, unchanged, won, units) for the over at (line0, odds0) against FanDuel's close."""
    beat = close[0] > line0 or (close[0] == line0 and close[1] < odds0 - 1e-9)
    same = close[0] == line0 and abs(close[1] - odds0) < 1e-9
    won = actual > line0
    return beat, same, won, (odds0 - 1) if won else (0.0 if actual == line0 else -1.0)


def band(x):
    if x is None:
        return "no projection"
    return "< 0" if x < 0 else "0-1" if x < 1 else ">= 1"


def premise(bx, team, x_name):
    """'sat' / 'played' for the absent player of this team, or None if he is not in the box."""
    from nba_news_watch import fold
    for p in bx.values():
        if p.get("_team") == team and fold(p.get("name", "")) == fold(x_name or ""):
            return "played" if p.get("played") == "1" else "sat"
    return "sat" if x_name else None            # not in the box at all: did not dress


def rows(now=None, box_get=None, results=None, lines=None, shadow=None, cache=None):
    import nba_clv as V
    import nba_reaction as RX
    results = RX.run(now) if results is None else results
    q = sqlite3.connect(f"file:{lines or LINES}?mode=ro", uri=True)
    tips = {g: t for g, t in q.execute("SELECT DISTINCT gid, tip_utc FROM quotes WHERE book='fd'")}
    cands = {}
    shadow = Path(shadow or SHADOW)
    if shadow.exists():
        sh = sqlite3.connect(f"file:{shadow}?mode=ro", uri=True)
        try:
            for gd, pid, stat, proj, thr in sh.execute(
                    "SELECT game_date, pid, stat, proj, thr FROM cands ORDER BY logged_at"):
                cands.setdefault((gd, pid, CAND_STAT.get(stat, stat)), (proj, thr))
        except sqlite3.OperationalError:
            pass
        sh.close()
    out = {}
    for r in results:
        x_by_team = {x["team"]: x["name"] for x in r["xs"]}
        for u in r["units"]["affected"]:
            if u["stat"] not in BOXKEY or u["gid"] not in tips:
                continue
            bx = final_box(u["gid"], box_get, cache=cache)
            p = (bx or {}).get(u["pid"])
            if not p or p.get("played") != "1":
                continue                                   # not final yet, or a DNP (void)
            x_name = x_by_team.get(p["_team"])
            k = (x_name, u["gid"], u["pid"], u["stat"])    # one absence x one prop (earliest trigger)
            if k in out:
                continue
            tl = RX.timeline(q.execute("SELECT seen_at, line, side, odds FROM quotes WHERE book='fd' AND gid=? "
                                       "AND pid=? AND stat=?", k[1:]).fetchall())
            m0 = RX.main_at(tl, r["t0"])
            close = V.close_of(q, u["gid"], u["pid"], u["stat"], tips[u["gid"]].replace("Z", ""), books=("fd",))
            if not m0 or not close:
                continue
            actual = sum(p["statistics"].get(s, 0) for s in BOXKEY[u["stat"]])
            beat, same, won, units = grade(m0[0], m0[1], close, actual)
            c = cands.get((RX._et_date(tips[u["gid"]].replace("Z", "")), u["pid"], u["stat"]))   # py3.10: no "Z"
            out[k] = {"gid": u["gid"], "stat": u["stat"], "src": r["src"], "beat": beat, "same": same,
                      "won": won, "units": units, "premise": premise(bx, p["_team"], x_name),
                      "band": band((c[0] - m0[0]) / c[1] if c and c[1] else None)}
    q.close()
    return list(out.values())


def slice_line(label, v, reps=2000):
    if not v:
        return f"  {label:<36} none"
    by = defaultdict(list)
    for x in v:
        by[x["gid"]].append(x)
    gs, rnd, res = list(by.values()), random.Random(7), []
    for _ in range(reps):
        pick = [x for _ in gs for x in rnd.choice(gs)]
        res.append(100 * sum(x["units"] for x in pick) / len(pick))
    res.sort()
    moved = [x for x in v if not x["same"]]
    return (f"  {label:<36} props {len(v):4d} · games {len(by):3d} · beat close {sum(x['beat'] for x in moved)}/"
            f"{len(moved)} ({100 * sum(x['beat'] for x in moved) / max(1, len(moved)):.0f}%) · over hit "
            f"{100 * sum(x['won'] for x in v) / len(v):.1f}% · ROI {100 * sum(x['units'] for x in v) / len(v):+.1f}% "
            f"[{res[int(.025 * reps)]:+.1f}, {res[int(.975 * reps)]:+.1f}]")


def report(rs):
    print("THE STALE-PROP LAB (amendment 25): OVER at FanDuel's main line when the news broke; information only")
    print(slice_line("everything", rs))
    for src in ("news", "report"):
        for pr in ("sat", "played"):
            print(slice_line(f"{src} · premise {pr}", [x for x in rs if x["src"] == src and x["premise"] == pr]))
    for s in ("points", "rebounds", "assists", "threes", "pra", "pts_reb", "pts_ast", "reb_ast"):
        print(slice_line(f"stat {s}", [x for x in rs if x["stat"] == s]))
    for b in ("no projection", "< 0", "0-1", ">= 1"):
        print(slice_line(f"model excess {b}", [x for x in rs if x["band"] == b]))
    n = sum(1 for x in rs if x["src"] == "news" and x["premise"] == "sat")
    print(f"  decision gate: {n}/300 graded news-first, premise-confirmed props (a later amendment, fit/hold)")


if __name__ == "__main__":
    report(rows())
