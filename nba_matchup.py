#!/usr/bin/env python3
"""Pace, matchup (defense vs position) and defensive play types — NBA_SPEED_PREREG.md amendment 30.

Box scores (cdn.nba.com liveData) are cached in nba_matchup.sqlite: team totals (possessions) and player rows
(starting position). Every feature is POINT-IN-TIME: only games before the game date, same season, shrunk to the
league with K_SHRINK games.
  PACE FACTOR     the opponent's possessions per game / the league mean
  MATCHUP FACTOR  the opponent's allowed stat per possession to B's position group (G / F / C) / the league mean
  proj_adj        proj x PACE FACTOR x MATCHUP FACTOR (exponents 1, nothing fit)
Play types (stats.nba.com Synergy) come as SEASON totals only, so they are snapshotted daily and used forward.

    python3 nba_matchup.py --fetch 2023-24 2024-25     # cache those seasons' box scores
    python3 nba_matchup.py --current                   # this season's finals + today's play-type snapshot
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "nba_matchup.sqlite"
K_SHRINK = 10
STATS = {"pts": ("pts",), "reb": ("reb",), "ast": ("ast",), "pra": ("pts", "reb", "ast"),
         "pts_reb": ("pts", "reb"), "pts_ast": ("pts", "ast"), "reb_ast": ("reb", "ast")}
GROUP = {"PG": "G", "SG": "G", "G": "G", "SF": "F", "PF": "F", "F": "F", "C": "C"}
PLAY_TYPES = ("PRBallHandler", "PRRollman", "Isolation", "Spotup", "Postup", "Handoff", "OffScreen", "Transition",
              "Cut", "Putback")
DDL = """
CREATE TABLE IF NOT EXISTS games (gid TEXT PRIMARY KEY, season TEXT, date TEXT, home TEXT, away TEXT);
CREATE TABLE IF NOT EXISTS team_games (gid TEXT, team TEXT, opp TEXT, fga REAL, fta REAL, oreb REAL, tov REAL,
    PRIMARY KEY (gid, team));
CREATE TABLE IF NOT EXISTS player_games (gid TEXT, team TEXT, pid INTEGER, pos TEXT, starter INTEGER, min REAL,
    pts REAL, reb REAL, ast REAL, fg3m REAL, stl REAL, blk REAL, tov REAL, PRIMARY KEY (gid, pid));
CREATE TABLE IF NOT EXISTS playtypes (snap TEXT, season TEXT, side TEXT, grouping TEXT, id INTEGER, abbr TEXT,
    play_type TEXT, poss_pct REAL, ppp REAL, pctile REAL, poss REAL, PRIMARY KEY (snap, side, grouping, id, play_type));
"""


def connect(path=None):
    con = sqlite3.connect(path or DB, timeout=60)
    con.executescript(DDL)
    have = {r[1] for r in con.execute("PRAGMA table_info(player_games)")}
    for col in ("fg3m", "stl", "blk", "tov"):          # added for the prop research page (threes, etc.)
        if col not in have:
            con.execute(f"ALTER TABLE player_games ADD COLUMN {col} REAL")
    return con


def season_of(date):
    """'2023-24' for any date from August 2023 to July 2024."""
    y = int(date[:4])
    y = y if int(date[5:7]) >= 8 else y - 1
    return f"{y}-{str(y + 1)[2:]}"


def regular_season_gids(season):
    """Every regular-season game id of a season: 002YY00001 .. 002YY01230."""
    yy = season[2:4]
    return [f"002{yy}{i:05d}" for i in range(1, 1231)]


def _minutes(s):
    """'PT34M12.00S' -> 34.2"""
    try:
        s = str(s or "")
        m = s.split("PT")[1].split("M")[0] if "PT" in s else "0"
        sec = s.split("M")[1].rstrip("S") if "M" in s else "0"
        return int(m or 0) + float(sec or 0) / 60
    except (IndexError, ValueError):
        return 0.0


def parse_box(b):
    """A cdn.nba.com liveData game dict -> (game row, [team rows], [player rows]), or None if not final."""
    if b.get("gameStatus") != 3:
        return None
    utc = dt.datetime.fromisoformat(b["gameTimeUTC"].replace("Z", "+00:00"))
    from zoneinfo import ZoneInfo
    date = utc.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    h, a = b["homeTeam"], b["awayTeam"]
    game = (b["gameId"], season_of(date), date, h["teamTricode"], a["teamTricode"])
    teams, players = [], []
    for side, other in ((h, a), (a, h)):
        st = side.get("statistics") or {}
        teams.append((b["gameId"], side["teamTricode"], other["teamTricode"], st.get("fieldGoalsAttempted", 0),
                      st.get("freeThrowsAttempted", 0), st.get("reboundsOffensive", 0), st.get("turnovers", 0)))
        for p in side["players"]:
            s = p.get("statistics") or {}
            mn = _minutes(s.get("minutes"))
            if str(p.get("played")) != "1" or mn <= 0:
                continue
            players.append((b["gameId"], side["teamTricode"], int(p["personId"]), p.get("position") or "",
                            int(str(p.get("starter")) == "1"), round(mn, 2), s.get("points", 0),
                            s.get("reboundsTotal", 0), s.get("assists", 0), s.get("threePointersMade", 0),
                            s.get("steals", 0), s.get("blocks", 0), s.get("turnovers", 0)))
    return game, teams, players


def fetch(gids, con=None, get=None, workers=8):
    """Cache the box scores of `gids` not cached yet. Returns (stored, not final / failed)."""
    con = con or connect()
    # a game cached before fg3m/stl/blk/tov were kept is fetched again
    have = {g for (g,) in con.execute("SELECT gid FROM games WHERE gid NOT IN "
                                      "(SELECT DISTINCT gid FROM player_games WHERE fg3m IS NULL)")}
    todo = [g for g in gids if g not in have]
    if get is None:
        import nba_rosters as R
        get = lambda g: R._get(R.BOX.format(g))["game"]

    def one(g):
        try:
            return parse_box(get(g))
        except Exception:                                                    # noqa: BLE001
            return None
    stored = missed = 0
    with ThreadPoolExecutor(workers) as ex:
        for res in ex.map(one, todo):
            if not res:
                missed += 1
                continue
            game, teams, players = res
            con.execute("INSERT OR REPLACE INTO games VALUES (?,?,?,?,?)", game)
            con.executemany("INSERT OR REPLACE INTO team_games VALUES (?,?,?,?,?,?,?)", teams)
            con.executemany("INSERT OR REPLACE INTO player_games (gid, team, pid, pos, starter, min, pts, reb, ast, "
                            "fg3m, stl, blk, tov) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", players)
            stored += 1
    con.commit()
    return stored, missed


class Season:
    """Point-in-time pace and matchup factors for one season, from the cache."""

    def __init__(self, con, season, index_pos=None):
        self.games = {g: (d, h, a) for g, d, h, a in con.execute(
            "SELECT gid, date, home, away FROM games WHERE season=?", (season,))}
        poss1 = {}
        for g, team, opp, fga, fta, oreb, tov in con.execute(
                "SELECT t.* FROM team_games t JOIN games g ON g.gid = t.gid WHERE g.season=?", (season,)):
            poss1[(g, team)] = fga + 0.44 * fta - oreb + tov
        self.poss = {}                                      # (gid, team) -> the game's possessions
        for (g, team), p in poss1.items():
            opp = [t for (gg, t) in poss1 if gg == g and t != team]
            if opp:
                self.poss[(g, team)] = 0.5 * (p + poss1[(g, opp[0])])
        rows = con.execute("SELECT p.gid, p.team, p.pid, p.pos, p.starter, p.pts, p.reb, p.ast FROM player_games p "
                           "JOIN games g ON g.gid = p.gid WHERE g.season=?", (season,)).fetchall()
        starts = defaultdict(list)                          # pid -> [(date, group)] of his starts
        for g, team, pid, pos, starter, *_ in rows:
            if starter and GROUP.get(pos):
                starts[pid].append((self.games[g][0], GROUP[pos]))
        for v in starts.values():
            v.sort()
        self.starts, self.index_pos = starts, index_pos or {}
        season_group = {pid: Counter(gr for _, gr in v).most_common(1)[0][0] for pid, v in starts.items()}
        # defense: per (team, date) what the OPPONENT's players of each group produced, and the game's possessions
        allowed = defaultdict(lambda: defaultdict(float))   # (defending team, gid) -> {(group, stat): total}
        for g, team, pid, pos, starter, pts, reb, ast in rows:
            gr = GROUP.get(pos) if starter else season_group.get(pid) or self._index_group(pid)
            if not gr:
                continue
            d, h, a = self.games[g]
            defender = a if team == h else h
            for s, v in (("pts", pts), ("reb", reb), ("ast", ast)):
                allowed[(defender, g)][(gr, s)] += v
        self.by_team = defaultdict(list)                    # team -> [(date, poss, {(group, stat): allowed})]
        for (g, team), p in self.poss.items():
            self.by_team[team].append((self.games[g][0], p, dict(allowed.get((team, g), {}))))
        for v in self.by_team.values():
            v.sort(key=lambda x: x[0])
        self.dates = {t: [x[0] for x in v] for t, v in self.by_team.items()}
        self.league = sorted(((x[0], x[1], x[2]) for v in self.by_team.values() for x in v), key=lambda x: x[0])
        self.league_dates = [x[0] for x in self.league]
        self._lg, self._tm = {}, {}                          # memo: date -> league; (team, date) -> its sums

    def _index_group(self, pid):
        pos = (self.index_pos.get(pid) or "")[:1]
        return GROUP.get(pos)

    def group(self, pid, date):
        """B's position group: his most frequent start before `date` this season, else the index, else None."""
        before = [gr for d, gr in self.starts.get(pid, []) if d < date]
        if before:
            return Counter(before).most_common(1)[0][0]
        return self._index_group(pid)

    def _league_before(self, date):
        if date not in self._lg:
            i = bisect.bisect_left(self.league_dates, date)
            games = self.league[:i]
            n = len(games)
            if not n:
                self._lg[date] = None
            else:
                poss = sum(x[1] for x in games)
                tot = defaultdict(float)
                for _, _, al in games:
                    for k, v in al.items():
                        tot[k] += v
                self._lg[date] = (n, poss / n, {k: v / poss for k, v in tot.items()})
        return self._lg[date]

    def _team_before(self, team, date):
        k = (team, date)
        if k not in self._tm:
            i = bisect.bisect_left(self.dates[team], date)
            mine = self.by_team[team][:i]
            tot = defaultdict(float)
            for _, _, al in mine:
                for kk, v in al.items():
                    tot[kk] += v
            self._tm[k] = (len(mine), sum(x[1] for x in mine), tot)
        return self._tm[k]

    def factors(self, opp, date, pid, league=None):
        """(pace_factor, {stat: matchup_factor}) for B (pid) against `opp` on `date`; 1.0 where unknown."""
        lg = league or self._league_before(date)
        out = {s: 1.0 for s in STATS}
        if not lg or opp not in self.by_team:
            return 1.0, out
        _, lg_poss, lg_rate = lg
        n, poss, tot = self._team_before(opp, date)
        if not n:
            return 1.0, out
        pace = (n * (poss / n) + K_SHRINK * lg_poss) / (n + K_SHRINK) / lg_poss
        gr = self.group(pid, date)
        if gr:
            for s, parts in STATS.items():
                lg_r = sum(lg_rate.get((gr, p), 0.0) for p in parts)
                if lg_r <= 0:
                    continue
                r = sum(tot.get((gr, p), 0.0) for p in parts) / poss
                out[s] = (n * r + K_SHRINK * lg_r) / (n + K_SHRINK) / lg_r
        return pace, out


def snapshot_playtypes(con=None, season=None, get=None, snap=None):
    """AMENDMENT 30: today's season-to-date Synergy play types — team DEFENSIVE and player OFFENSIVE."""
    con = con or connect()
    snap = snap or dt.date.today().isoformat()
    season = season or season_of(snap)
    if get is None:
        import nba_tracking as T
        from curl_cffi import requests as cr
        get = lambda u: cr.get(u, impersonate="chrome", timeout=60, headers=T.H).json()
    n = 0
    for side, grouping in (("team", "defensive"), ("player", "offensive")):
        for pt in PLAY_TYPES:
            u = ("https://stats.nba.com/stats/synergyplaytypes?LeagueID=00&PerMode=Totals&PlayType=" + pt +
                 f"&PlayerOrTeam={'T' if side == 'team' else 'P'}&SeasonType=Regular%20Season&SeasonYear={season}"
                 f"&TypeGrouping={grouping}")
            try:
                rs = get(u)["resultSets"][0]
            except Exception:                                                # noqa: BLE001
                continue
            ix = {h: k for k, h in enumerate(rs["headers"])}
            idk, ab = ("TEAM_ID", "TEAM_ABBREVIATION") if side == "team" else ("PLAYER_ID", "TEAM_ABBREVIATION")
            for r in rs["rowSet"]:
                con.execute("INSERT OR REPLACE INTO playtypes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (snap, season, side, grouping, r[ix[idk]], r[ix[ab]], pt, r[ix["POSS_PCT"]], r[ix["PPP"]],
                             r[ix["PERCENTILE"]], r[ix["POSS"]]))
                n += 1
    con.commit()
    return n


def scheme_cell(con, pid, opp, snap):
    """AMENDMENT 30 (information): B's main offensive play type and the opponent's defensive percentile on it, from
    the latest snapshot on or before `snap`. -> (play_type, 'tough' / 'neutral' / 'soft') or (None, None)."""
    row = con.execute("SELECT MAX(snap) FROM playtypes WHERE snap <= ?", (snap,)).fetchone()
    s = row[0] if row else None
    if not s:
        return None, None
    pt = con.execute("SELECT play_type FROM playtypes WHERE snap=? AND side='player' AND id=? ORDER BY poss DESC LIMIT 1",
                     (s, pid)).fetchone()
    if not pt:
        return None, None
    d = con.execute("SELECT pctile FROM playtypes WHERE snap=? AND side='team' AND abbr=? AND play_type=?",
                    (s, opp, pt[0])).fetchone()
    if not d or d[0] is None:
        return pt[0], None
    return pt[0], ("tough" if d[0] >= 0.67 else "soft" if d[0] <= 0.33 else "neutral")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", nargs="*", help="seasons to cache, e.g. 2023-24 2024-25")
    ap.add_argument("--current", action="store_true", help="this season's finals + a play-type snapshot")
    ap.add_argument("--last", action="store_true", help="also cache last season (the research page's game logs)")
    a = ap.parse_args()
    con = connect()
    for s in a.fetch or []:
        print(s, "stored %d, not final or failed %d" % fetch(regular_season_gids(s), con))
    if a.current:
        import nba_rosters as R
        finals = [g["gid"] for g in R.schedule() if g["status"] == 3]      # this season's finished games only
        print(season_of(dt.date.today().isoformat()), "stored %d, not final or failed %d" % fetch(finals, con))
        if a.last:
            cur = season_of(dt.date.today().isoformat())
            prev = f"{int(cur[:4]) - 1}-{cur[2:4]}"
            print(prev, "stored %d, not final or failed %d" % fetch(regular_season_gids(prev), con))
        print("play-type rows:", snapshot_playtypes(con))
