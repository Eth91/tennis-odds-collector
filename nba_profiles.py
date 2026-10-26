#!/usr/bin/env python3
"""Prior-season basketball profiles for NBA_FILTER_SEARCH_PREREG.md. MAC-ONLY (stats.nba.com).

Each is a FULL-SEASON number, used only for bets in the FOLLOWING season, so nothing looks ahead:
  player_zones      (season, pid)   share of FGA at the rim / paint / mid-range / corner 3 / above-break 3
  team_opp_zones    (season, team)  opponents' FG% allowed in each of those zones (defense type)
  player_playtypes  (season, pid, playtype)  frequency (share of possessions) and points per possession
  team_def_playtypes(season, team, playtype) points per possession ALLOWED on that play type
  team_games        (game_id, team) home/away and opponent, every regular-season game 2022-23..2024-25
                                    (the stored box scores lack home/away)

    python nba_profiles.py --fetch
"""
from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

from curl_cffi import requests as cr

HERE = Path(__file__).resolve().parent
DB = HERE / "nba_profiles.sqlite"
H = {"Referer": "https://www.nba.com/", "Origin": "https://www.nba.com", "Accept": "application/json",
     "x-nba-stats-origin": "stats", "x-nba-stats-token": "true"}
PROFILE_SEASONS = ["2022-23", "2023-24"]               # priors for the 2023-24 / 2024-25 bets
GAME_SEASONS = ["2022-23", "2023-24", "2024-25"]
PLAYTYPES = ["Isolation", "Transition", "PRBallHandler", "PRRollman", "Postup", "Spotup",
             "Handoff", "Cut", "OffScreen"]
ZONES = {"Restricted Area": "ra", "In The Paint (Non-RA)": "paint", "Mid-Range": "mid",
         "Corner 3": "c3", "Above the Break 3": "ab3"}
COMMON = ("&SeasonType=Regular%20Season&LeagueID=00&PerMode=Totals&LastNGames=0&Month=0&OpponentTeamID=0"
          "&PORound=0&Period=0&TeamID=0&PaceAdjust=N&PlusMinus=N&Rank=N&DateFrom=&DateTo=&GameScope="
          "&PlayerExperience=&PlayerPosition=&StarterBench=&Outcome=&Location=&SeasonSegment="
          "&VsConference=&VsDivision=&College=&Conference=&Country=&DraftPick=&DraftYear=&Division="
          "&Height=&Weight=&ShotClockRange=&GameSegment=")
DDL = """
CREATE TABLE IF NOT EXISTS player_zones (season TEXT, pid INTEGER, fga REAL, ra REAL, paint REAL,
    mid REAL, c3 REAL, ab3 REAL, PRIMARY KEY (season, pid));
CREATE TABLE IF NOT EXISTS team_opp_zones (season TEXT, team TEXT, ra REAL, paint REAL, mid REAL,
    c3 REAL, ab3 REAL, PRIMARY KEY (season, team));
CREATE TABLE IF NOT EXISTS player_playtypes (season TEXT, pid INTEGER, playtype TEXT, freq REAL,
    ppp REAL, poss REAL, PRIMARY KEY (season, pid, playtype));
CREATE TABLE IF NOT EXISTS team_def_playtypes (season TEXT, team TEXT, playtype TEXT, ppp REAL,
    freq REAL, PRIMARY KEY (season, team, playtype));
CREATE TABLE IF NOT EXISTS team_games (game_id TEXT, team TEXT, date TEXT, home INTEGER,
    opp TEXT, PRIMARY KEY (game_id, team));
"""


def _get(url, tries=4):
    for k in range(tries):
        try:
            r = cr.get(url, impersonate="chrome", timeout=60, headers=H)
            if r.status_code == 200:
                rs = r.json()["resultSets"]
                return rs[0] if isinstance(rs, list) else rs
            err = f"HTTP {r.status_code}"
        except Exception as e:
            err = type(e).__name__
        time.sleep(5 * (k + 1))
    raise RuntimeError(f"gave up ({err}): {url[:90]}")


def _zone_index(rs):
    """Nested column groups -> {zone_key: (fgm_col, fga_col, pct_col)} by position."""
    groups = rs["headers"][0]["columnNames"]
    cols = rs["headers"][-1]["columnNames"]
    span = rs["headers"][0].get("columnSpan", 3)
    skip = rs["headers"][0].get("columnsToSkip", 0)
    out = {}
    for gi, g in enumerate(groups):
        if g in ZONES:
            base = skip + gi * span
            out[ZONES[g]] = (base, base + 1, base + 2)
    return out, cols


def fetch():
    con = sqlite3.connect(DB)
    con.executescript(DDL)
    for season in PROFILE_SEASONS:
        rs = _get("https://stats.nba.com/stats/leaguedashplayershotlocations?Season=" + season +
                  "&DistanceRange=By%20Zone&MeasureType=Base" + COMMON)
        zi, cols = _zone_index(rs)
        pid_i = cols.index("PLAYER_ID")
        for r in rs["rowSet"]:
            fga = {z: (r[i[1]] or 0) for z, i in zi.items()}
            tot = sum(fga.values())
            if tot <= 0:
                continue
            con.execute("INSERT OR REPLACE INTO player_zones VALUES (?,?,?,?,?,?,?,?)",
                        (season, int(r[pid_i]), tot, *[fga[z] / tot for z in ("ra", "paint", "mid", "c3", "ab3")]))
        rs = _get("https://stats.nba.com/stats/leaguedashteamshotlocations?Season=" + season +
                  "&DistanceRange=By%20Zone&MeasureType=Opponent" + COMMON)
        zi, cols = _zone_index(rs)
        name_i = cols.index("TEAM_NAME")
        for r in rs["rowSet"]:
            con.execute("INSERT OR REPLACE INTO team_opp_zones VALUES (?,?,?,?,?,?,?)",
                        (season, r[name_i], *[r[zi[z][2]] for z in ("ra", "paint", "mid", "c3", "ab3")]))
        for pt in PLAYTYPES:
            for who, grouping, table in (("P", "offensive", "player"), ("T", "defensive", "team")):
                rs = _get("https://stats.nba.com/stats/synergyplaytypes?LeagueID=00&PerMode=Totals"
                          f"&PlayType={pt}&PlayerOrTeam={who}&SeasonType=Regular%20Season"
                          f"&SeasonYear={season}&TypeGrouping={grouping}")
                ix = {h: k for k, h in enumerate(rs["headers"])}
                for r in rs["rowSet"]:
                    if table == "player":
                        con.execute("INSERT OR REPLACE INTO player_playtypes VALUES (?,?,?,?,?,?)",
                                    (season, int(r[ix["PLAYER_ID"]]), pt, r[ix["POSS_PCT"]],
                                     r[ix["PPP"]], r[ix["POSS"]]))
                    else:
                        con.execute("INSERT OR REPLACE INTO team_def_playtypes VALUES (?,?,?,?,?)",
                                    (season, r[ix["TEAM_ABBREVIATION"]], pt, r[ix["PPP"]],
                                     r[ix["POSS_PCT"]]))
                time.sleep(0.8)
        con.commit()
        print(f"{season}: zones + play types stored", flush=True)
    for season in GAME_SEASONS:
        rs = _get("https://stats.nba.com/stats/leaguegamelog?Counter=1000&DateFrom=&DateTo=&Direction=DESC"
                  f"&LeagueID=00&PlayerOrTeam=T&Season={season}&SeasonType=Regular%20Season&Sorter=DATE")
        ix = {h: k for k, h in enumerate(rs["headers"])}
        for r in rs["rowSet"]:
            mu = r[ix["MATCHUP"]]                      # "ATL vs. MIA" (home) / "ATL @ MIA" (away)
            home = 1 if " vs. " in mu else 0
            opp = mu.split(" vs. " if home else " @ ")[-1].strip()
            con.execute("INSERT OR REPLACE INTO team_games VALUES (?,?,?,?,?)",
                        (r[ix["GAME_ID"]], r[ix["TEAM_ABBREVIATION"]], r[ix["GAME_DATE"]], home, opp))
        con.commit()
        print(f"{season}: team games stored", flush=True)
    for t in ("player_zones", "team_opp_zones", "player_playtypes", "team_def_playtypes", "team_games"):
        print(f"  {t}: {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:,} rows")
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", required=True)
    ap.parse_args()
    fetch()
