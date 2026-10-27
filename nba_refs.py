#!/usr/bin/env python3
"""Referees for the props page: docs/refs.json — tonight's crews (official.nba.com's referee assignments, posted
about 9 AM ET) and how each official's games have run this season and last: fouls, free throws, points and pace,
both teams together, against the league's games over the same span.

Each final game's officials and team totals come from its cdn.nba.com liveData box score, fetched once (a final box
does not change) and kept in nba_refs.sqlite; which finals exist comes from nba_matchup.sqlite's games (read-only).

File: {generated_at, seasons, league: [n, pts, pf, fta, poss], refs: {pid: [name, n, pts, pf, fta, poss]},
       games: {gid: [[pid or null, name, role], ...]}}
  pts / pf / fta  both teams' points, personal fouls and free throw attempts a game
  poss            possessions a game (each team's FGA + 0.44 FTA - OREB + TOV, averaged)
  role            "Crew Chief", "Referee" or "Umpire"; pid null for an official with no game in the store yet

    python3 nba_refs.py --out /home/ubuntu/tennis-odds-collector/docs
"""
from __future__ import annotations

import argparse
import datetime as dt
import html as H
import json
import os
import re
import sqlite3
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DB = Path(__file__).resolve().parent / "nba_refs.sqlite"
ASSIGN_URL = "https://official.nba.com/referee-assignments/"
DDL = """CREATE TABLE IF NOT EXISTS games (gid TEXT PRIMARY KEY, season TEXT, date TEXT, pts REAL, pf REAL, fta REAL, poss REAL);
CREATE TABLE IF NOT EXISTS crew (gid TEXT, pid INTEGER, name TEXT, PRIMARY KEY (gid, pid));
CREATE TABLE IF NOT EXISTS assign (gid TEXT, pos INTEGER, name TEXT, role TEXT, seen_at TEXT, PRIMARY KEY (gid, pos));"""
ROLES = ("Crew Chief", "Referee", "Umpire")
# how official.nba.com names each team in its game column ("Washington @ Charlotte"); the two LA teams by nickname
CITY = {"ATL": "Atlanta", "BOS": "Boston", "BKN": "Brooklyn", "CHA": "Charlotte", "CHI": "Chicago", "CLE": "Cleveland",
        "DAL": "Dallas", "DEN": "Denver", "DET": "Detroit", "GSW": "Golden State", "HOU": "Houston", "IND": "Indiana",
        "LAC": "clippers", "LAL": "lakers", "MEM": "Memphis", "MIA": "Miami", "MIL": "Milwaukee", "MIN": "Minnesota",
        "NOP": "New Orleans", "NYK": "New York", "OKC": "Oklahoma City", "ORL": "Orlando", "PHI": "Philadelphia",
        "PHX": "Phoenix", "POR": "Portland", "SAC": "Sacramento", "SAS": "San Antonio", "TOR": "Toronto", "UTA": "Utah",
        "WAS": "Washington"}


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[.'`]", "", s)                                    # "J.T. Orr" is the page's "JT Orr"
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s.lower()).split())


def fits(name, tri):
    """Is the assignment page's team name `name` the team `tri`? Its city ("Washington", "Washington Wizards"), or for
    the LA teams the nickname."""
    n, c = _norm(name), _norm(CITY.get(tri, ""))
    return bool(c) and ((" " + c + " ") in (" " + n + " ") if tri not in ("LAC", "LAL") else c in n.split())   # whole words


def game_row(g):
    """A liveData game dict -> ((pts, pf, fta, poss), [(pid, name)]) for a final game, else None."""
    if g.get("gameStatus") != 3:
        return None
    tot, poss = [0.0, 0.0, 0.0], []
    for side in (g["homeTeam"], g["awayTeam"]):
        s = side.get("statistics") or {}
        f = lambda k: float(s.get(k) or 0)
        tot[0] += f("points"); tot[1] += f("foulsPersonal"); tot[2] += f("freeThrowsAttempted")
        poss.append(f("fieldGoalsAttempted") + .44 * f("freeThrowsAttempted") - f("reboundsOffensive") + f("turnoversTotal"))
    crew = [(int(o["personId"]), o.get("name") or "") for o in g.get("officials") or [] if o.get("personId")]
    return (tot[0], tot[1], tot[2], sum(poss) / 2), crew


def fetch_games(con, mcon, seasons, get=None, workers=4):
    """Store every final game in `seasons` (nba_matchup's games) not stored yet. Returns (stored, failed)."""
    have = {g for (g,) in con.execute("SELECT gid FROM games")}
    marks = ",".join("?" * len(seasons))
    todo = [r for r in mcon.execute(f"SELECT gid, season, date FROM games WHERE season IN ({marks}) AND home_pts IS NOT NULL "
                                    "ORDER BY date DESC", list(seasons)) if r[0] not in have]
    if get is None:
        import nba_rosters as R
        get = lambda gid: R._get(R.BOX.format(gid))["game"]

    def one(r):
        try:
            return game_row(get(r[0]))
        except Exception:                                                     # noqa: BLE001
            return None
    stored = failed = 0
    with ThreadPoolExecutor(workers) as ex:
        for (gid, season, date), row in zip(todo, ex.map(one, todo)):
            if not row or not row[1]:                                         # not final, or no officials listed
                failed += 1
                continue
            con.execute("INSERT OR REPLACE INTO games VALUES (?,?,?,?,?,?,?)", (gid, season, date) + tuple(round(v, 2) for v in row[0]))
            con.executemany("INSERT OR REPLACE INTO crew VALUES (?,?,?)", [(gid, pid, nm) for pid, nm in row[1]])
            stored += 1
    con.commit()
    return stored, failed


def parse_assign(page):
    """The NBA table of the assignments page -> [(away name, home name, [(name, role)])]; the WNBA table is skipped."""
    a, b = page.find("NBA Referee Assignments"), page.find("WNBA Referee Assignments")
    part = page[a:b] if a >= 0 and b > a else page[a:] if a >= 0 else page
    cell = lambda c: H.unescape(" ".join(re.sub(r"<[^>]+>", " ", c).split()))
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", part, re.S):
        cells = [cell(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        if len(cells) < 4 or "@" not in cells[0]:
            continue
        away, home = [x.strip() for x in cells[0].split("@", 1)]
        crew = [(re.sub(r"\s*\(#\d+\)\s*$", "", c).strip(), ROLES[k]) for k, c in enumerate(cells[1:4]) if c.strip()]
        out.append((away, home, crew))
    return out


def match(rows, games):
    """Assignment rows -> {gid: [(name, role)]}; games: [{gid, away, home}] (the slate). A row with no game is dropped."""
    out = {}
    for away, home, crew in rows:
        g = next((g for g in games if fits(away, g["away"]) and fits(home, g["home"])), None)
        if g:
            out[g["gid"]] = crew
    return out


def store_assign(con, assigned, now):
    for gid, crew in assigned.items():
        con.execute("DELETE FROM assign WHERE gid=?", (gid,))
        con.executemany("INSERT INTO assign VALUES (?,?,?,?,?)", [(gid, k, nm, role, now) for k, (nm, role) in enumerate(crew)])
    con.commit()


def build(con, seasons, gids, now):
    """The page's file: every official's averages over `seasons`, the league's, and the crews for `gids`."""
    marks = ",".join("?" * len(seasons))
    lg = con.execute(f"SELECT COUNT(*), AVG(pts), AVG(pf), AVG(fta), AVG(poss) FROM games WHERE season IN ({marks})", list(seasons)).fetchone()
    refs = {}
    for pid, name, n, pts, pf, fta, poss in con.execute(
            f"SELECT c.pid, MAX(c.name), COUNT(*), AVG(g.pts), AVG(g.pf), AVG(g.fta), AVG(g.poss) FROM crew c JOIN games g "
            f"ON g.gid = c.gid WHERE g.season IN ({marks}) GROUP BY c.pid", list(seasons)):
        refs[str(pid)] = [name, n, round(pts, 1), round(pf, 1), round(fta, 1), round(poss, 1)]
    # every spelling the box scores have used for an official ("Nate Cearly", "Nate Cearley") finds him
    by_name = {_norm(nm): pid for pid, nm in con.execute("SELECT DISTINCT pid, name FROM crew")}
    games = {}
    for gid in gids:
        rows = con.execute("SELECT name, role FROM assign WHERE gid=? ORDER BY pos", (gid,)).fetchall()
        if rows:
            games[gid] = [[by_name.get(_norm(nm)), nm, role] for nm, role in rows]
        else:                                                    # no assignment kept: the box's officials, if final
            crew = con.execute("SELECT pid, name FROM crew WHERE gid=? ORDER BY rowid", (gid,)).fetchall()
            if crew:
                games[gid] = [[pid, nm, ROLES[k] if k < 3 else ""] for k, (pid, nm) in enumerate(crew)]
    return {"generated_at": now, "seasons": list(seasons),
            "league": [lg[0]] + [round(v or 0, 1) for v in lg[1:]], "refs": refs, "games": games}


def main():
    import nba_matchup as MU
    import nba_research as R
    import nba_rosters as RO
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="the folder the page reads (docs)")
    a = ap.parse_args()
    con = sqlite3.connect(DB)
    con.executescript(DDL)
    mcon = sqlite3.connect(f"file:{MU.DB}?mode=ro", uri=True)
    now = dt.datetime.now(dt.timezone.utc)
    stamp = now.replace(microsecond=0).isoformat()
    today = (now.astimezone(R.ET) - dt.timedelta(hours=R.SLATE_ROLL_H)).date()
    cur = R.season_of(today.isoformat())
    seasons = (R.prev_season(cur), cur)
    stored, failed = fetch_games(con, mcon, seasons)
    sched = RO.schedule()
    dates = {(today + dt.timedelta(days=k)).isoformat() for k in (-1, 0, 1)}
    slate = [g for g in sched if g["date_et"] in dates]
    try:
        from curl_cffi import requests as cr
        r = cr.get(ASSIGN_URL, impersonate="chrome", timeout=30)
        assigned = match(parse_assign(r.text), [g for g in slate if g["date_et"] == today.isoformat()]) if r.status_code == 200 else {}
    except Exception as e:                                                    # noqa: BLE001
        print(f"nba_refs: assignments unavailable ({type(e).__name__})")
        assigned = {}
    store_assign(con, assigned, stamp)
    doc = build(con, seasons, [g["gid"] for g in slate], stamp)
    out = Path(a.out)
    tmp = out / ".refs.json.tmp"
    tmp.write_text(json.dumps(doc, separators=(",", ":")))
    os.replace(tmp, out / "refs.json")
    print(f"nba_refs: {stored} games stored, {failed} failed · {len(assigned)} crews today · {len(doc['refs'])} officials -> {out}")


if __name__ == "__main__":
    main()
