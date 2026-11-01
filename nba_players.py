#!/usr/bin/env python3
"""Every player's page, prop or not: docs/player/{pid}.json — his game logs for this season and last in the props
page's LOG_COLS (nba_research.game_logs, the same rows a prop's page charts) — and docs/player/index.json, the list
the page searches: [pid, name, team, position] for everyone on a roster now (the player index) who has a game —
and docs/player/roles.json, the role changes (roles()).

    python3 nba_players.py --out /home/ubuntu/tennis-odds-collector/docs/player
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
from pathlib import Path
from collections import Counter
from statistics import median

import nba_research as R


def _write(path, doc):
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":")))
    os.replace(tmp, path)


# how far a stat a game must move over his last 3 games off his baseline for him to be listed on it (the page's Roles
# switch); a player is in the file if any one of them moved that far
ROLE_MOVE = {"min": 4.0, "fga": 3.0, "fg3a": 2.0, "pot_ast": 2.5, "reb_ch": 3.0}
ROLE_MIN = ROLE_MOVE["min"]
TRACKED = ("pot_ast", "reb_ch")
# the NBA's rebound chances are not comparable across seasons: 1.37-1.54 per box rebound in 2025-26, 1.89 in 2026-27 at
# the same 0.18 rebounds a minute (potential assists held at 1.8 per assist). Rebound chances move only against this season
SAME_SEASON_ONLY = ("reb_ch",)
# early in a season there is too little of it to judge a player's last 3 games against: until the median team has
# played RECENT_FROM games, Roles compares his season so far with last season (LAST_MIN_GP+ games there, any team); from
# then on, his last 3 games with his season average (SEASON_MIN_GP+ games, the last 3 among them: the average the
# player's page shows). The file says which ("mode")
RECENT_FROM = 5
LAST_MIN_GP = 10
SEASON_MIN_GP = 5


def lined_players(q, season):
    """Players a book (FanDuel or DraftKings) has posted a prop line for this season (nba_lines.sqlite quotes): Roles
    lists only these, not players no one can bet."""
    return {int(pid) for (pid,) in q.execute("SELECT DISTINCT pid FROM quotes WHERE seen_at >= ? AND pid IS NOT NULL",
                                             (f"{season[:4]}-08-01",))}


def roles_mode(team_games):
    gp = sorted(len(v) for v in team_games.values())
    return "recent" if gp and gp[len(gp) // 2] >= RECENT_FROM else "season"
REG_MPG = 18.0      # a teammate this regular (minutes a game this season, 3+ games) who sat 2 of the last 3 is named


def roles(logs, idx, season, team_games, lined=None):
    """Players whose minutes, shots (FGA, 3PTA), potential assists or rebound chances a game moved by at least
    ROLE_MOVE, in roles_mode's comparison: "season" (his games this season for his team against all of last season's,
    "was_team" set when he played most of them elsewhere) or "recent" (his last 3 games against his season average, the
    last 3 included). Each with every stat now and before ("st", None where tracking has too few games or the stat does
    not compare across seasons), his usage, his starts ([starts now, starts before, games before, games now]: "before" is
    the games ahead of his last 3, so a new starter reads as one), and the regular
    teammates who sat 2 of his team's last 3 games. logs: {pid: LOG_COLS rows}; team_games: {team: [gid, ...] this
    season, oldest first}; lined: lined_players (None: everyone). Biggest minutes move first."""
    C = {c: k for k, c in enumerate(R.LOG_COLS)}
    played = {}                                              # (team, gid) -> pids who played
    for pid, rows in logs.items():
        for r in rows:
            played.setdefault((r[C["team"]], r[C["gid"]]), set()).add(pid)
    mean = lambda xs: sum(xs) / len(xs) if xs else None
    mode, last = roles_mode(team_games), R.prev_season(season)
    out = []
    for pid, rows in logs.items():
        info = idx.get(str(pid))
        if not info or (lined is not None and pid not in lined):
            continue
        team = info[0]
        cur = [r for r in rows if R.season_of(r[C["date"]]) == season and r[C["team"]] == team]
        last4 = (team_games.get(team) or [])[-4:]
        if len(cur) < 3 or any(r[C["gid"]] not in last4 for r in cur[-3:]):
            continue                                         # not playing lately: a return or an absence, not a role
        was_team = None
        if mode == "recent":
            recent, base, before, frm = cur[-3:], cur, cur[:-3], "this season"
            if len(cur) < SEASON_MIN_GP:
                continue
        else:
            recent, frm = cur, "last season"
            base = before = [r for r in rows if R.season_of(r[C["date"]]) == last]
            if len(base) < LAST_MIN_GP:
                continue
            top = Counter(r[C["team"]] for r in base).most_common(1)[0][0]
            was_team = top if top != team else None              # a new team: the biggest role change of all
        st = {}
        for k in ROLE_MOVE:
            now, was = [r[C[k]] for r in recent if r[C[k]] is not None], [r[C[k]] for r in base if r[C[k]] is not None]
            avg = median if k in TRACKED else mean            # the tracking feed has bad nights: a typical game, not the mean
            st[k] = [round(avg(now), 1), round(avg(was), 1)] if len(now) >= 2 and len(was) >= 3 and \
                not (k in SAME_SEASON_ONLY and frm == "last season") else None
        if not any(v and abs(v[0] - v[1]) >= ROLE_MOVE[k] for k, v in st.items()):
            continue
        d = mean([r[C["min"]] for r in recent]) - mean([r[C["min"]] for r in base])
        us = lambda rs: mean([r[C["usg"]] for r in rs if r[C["usg"]] is not None])
        last3 = (team_games.get(team) or [])[-3:]
        regs = []
        for mate, mrows in logs.items():
            mi = idx.get(str(mate))
            if mate == pid or not mi or mi[0] != team:
                continue
            mcur = [r for r in mrows if R.season_of(r[C["date"]]) == season and r[C["team"]] == team and r[C["gid"]] not in last3]
            if len(mcur) >= 3 and mean([r[C["min"]] for r in mcur]) >= REG_MPG and \
                    sum(1 for g in last3 if mate in played.get((team, g), ())) <= len(last3) - 2:
                regs.append(mi[1])
        out.append({"pid": pid, "name": info[1], "team": team, "d_min": round(d, 1),
                    "min": [round(mean([r[C["min"]] for r in recent]), 1), round(mean([r[C["min"]] for r in base]), 1)],
                    "usg": [None if us(recent) is None else round(us(recent), 1), None if us(base) is None else round(us(base), 1)],
                    "starts": [sum(r[C["starter"]] or 0 for r in recent), sum(r[C["starter"]] or 0 for r in before), len(before), len(recent)],
                    "base": frm, "was_team": was_team, "out": regs, "st": st})
    return sorted(out, key=lambda e: -abs(e["d_min"]))


def build(mcon, out, idx, season, trk=None, lined=None):
    """Write one file per player with games, and the index. Returns the number of players written."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    pids = [int(k) for k in idx]
    logs = R.game_logs(mcon, pids, (R.prev_season(season), season), trk)
    rows = []
    for pid in pids:
        lg = logs.get(pid)
        if not lg:
            continue
        team, name, pos = idx[str(pid)][:3]
        _write(out / f"{pid}.json", {"pid": pid, "name": name, "team": team, "pos": pos or "", "logs": lg})
        rows.append([pid, name, team, pos or ""])
    _write(out / "index.json", {"season": season, "log_cols": list(R.LOG_COLS),
                                "players": sorted(rows, key=lambda r: r[1])})
    team_games = {}
    for gid, h, a in mcon.execute("SELECT gid, home, away FROM games WHERE season=? AND home_pts IS NOT NULL "
                                  "ORDER BY date, gid", (season,)):
        for t in (h, a):
            team_games.setdefault(t, []).append(gid)
    _write(out / "roles.json", {"season": season, "thresholds": ROLE_MOVE, "mode": roles_mode(team_games),
                                "rows": roles(logs, idx, season, team_games, lined)})
    return len(rows)


def main():
    import nba_matchup as MU
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="the folder the page reads (docs/player)")
    a = ap.parse_args()
    mcon = sqlite3.connect(f"file:{MU.DB}?mode=ro", uri=True)
    idx = json.loads(R.INDEX.read_text()).get("players", {})
    season = R.season_of(dt.datetime.now(R.ET).date().isoformat())
    q = R._ro(R.LINES)
    n = build(mcon, a.out, idx, season, R._ro(R.TRACKING), lined_players(q, season) if q else None)
    print(f"nba_players: {n} players -> {a.out}")


if __name__ == "__main__":
    main()
