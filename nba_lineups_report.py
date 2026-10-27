#!/usr/bin/env python3
"""How good is NBA.com's lineup file at the cutoff? Per team-game: status at tip − 30 min (Expected / Confirmed /
none), whether the starters seen then are the ones who started, and when the lineup was first all Confirmed.
"Who started" is the file's final snapshot (after tip, the file holds the actual lineup).
    python3 nba_lineups_report.py [--db nba_lineups.sqlite] [--tips nba_lines.sqlite] [--json OUT]
"""
import argparse
import datetime as dt
import json
import sqlite3
import zlib
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CUTOFF = dt.timedelta(minutes=30)


def team_states(db):
    """{(gid, team): [(fetched_at, starters frozenset, status, game started)]} in time order."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out = defaultdict(list)
    for t, b in con.execute("SELECT fetched_at, body FROM snaps ORDER BY fetched_at"):
        at = dt.datetime.fromisoformat(t)
        for g in json.loads(zlib.decompress(b)).get("games", []):
            for side in ("homeTeam", "awayTeam"):
                ps = [p for p in g[side]["players"] if p.get("position")]
                st = {p.get("lineupStatus") for p in ps}
                status = "none" if not ps else ("Confirmed" if st == {"Confirmed"} else "Expected")
                out[(g["gameId"], g[side]["teamAbbreviation"])].append(
                    (at, frozenset(p["personId"] for p in ps), status, (g.get("gameStatus") or 1) >= 2))
    return out


def tips(lines_db, gids):
    con = sqlite3.connect(f"file:{lines_db}?mode=ro", uri=True)
    q = f"SELECT gid, MIN(tip_utc) FROM quotes WHERE gid IN ({','.join('?' * len(gids))}) GROUP BY gid"
    return {g: dt.datetime.fromisoformat(t.replace("Z", "+00:00")) for g, t in con.execute(q, list(gids)) if t}


def report(db, lines_db, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    states = team_states(db)
    tp = tips(lines_db, {g for g, _ in states})
    rows = []
    for (gid, team), h in sorted(states.items()):
        tip = tp.get(gid)
        if tip is None:
            continue
        at_cut = [x for x in h if x[0] <= tip - CUTOFF]
        after = [x for x in h if x[3]]                                 # the game has begun: the actual starters
        if not after:
            continue
        final = after[-1][1]
        cut = at_cut[-1] if at_cut else None
        conf = next((x[0] for x in h if x[2] == "Confirmed"), None)
        rows.append({"gid": gid, "team": team, "tip": tip.isoformat(), "status_at_cutoff": cut[2] if cut else "no snapshot",
                     "starters_right_at_cutoff": (len(cut[1] & final) if cut and cut[1] else None),
                     "confirmed_min_before_tip": round((tip - conf).total_seconds() / 60) if conf and conf <= tip else None})
    n = len(rows)
    summ = {"team_games": n,
            "status_at_cutoff": {s: sum(r["status_at_cutoff"] == s for r in rows) for s in ("Confirmed", "Expected", "none", "no snapshot")},
            "all_5_right_at_cutoff": sum(r["starters_right_at_cutoff"] == 5 for r in rows),
            "starters_known_at_cutoff": sum(r["starters_right_at_cutoff"] is not None for r in rows),
            "confirmed_min_before_tip": sorted(r["confirmed_min_before_tip"] for r in rows if r["confirmed_min_before_tip"] is not None)}
    return summ, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(HERE / "nba_lineups.sqlite"))
    ap.add_argument("--tips", default=str(HERE / "nba_lines.sqlite"))
    ap.add_argument("--json")
    a = ap.parse_args()
    summ, rows = report(a.db, a.tips)
    for r in rows:
        print(f"{r['gid']} {r['team']}  at cutoff: {r['status_at_cutoff']:11s} starters right: {r['starters_right_at_cutoff']}  "
              f"confirmed {r['confirmed_min_before_tip']} min before tip")
    print(json.dumps(summ))
    if a.json:
        Path(a.json).write_text(json.dumps({"summary": summ, "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
