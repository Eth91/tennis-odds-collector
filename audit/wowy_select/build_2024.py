"""2024-25 regular season on the Mac: liveData box scores (starters, slots, names, minutes) into m2425.sqlite, then
the lineups (nba_onoff) into onoff_2024.sqlite. Read-only for every live store."""
import re, sqlite3, sys, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/Users/ethandown/nba-engine")
import nba_onoff as O, nba_rosters as R
m = sqlite3.connect("m2425.sqlite")
m.executescript("""CREATE TABLE IF NOT EXISTS games (gid TEXT PRIMARY KEY, season TEXT, date TEXT, home TEXT, away TEXT,
  home_name TEXT, away_name TEXT, home_pts INTEGER);
CREATE TABLE IF NOT EXISTS player_games (gid TEXT, pid INTEGER, team TEXT, starter INTEGER, pos TEXT, name TEXT, min REAL,
  pts INTEGER, reb INTEGER, ast INTEGER, fg3m INTEGER, fga INTEGER, PRIMARY KEY (gid, pid));""")
have = {g for (g,) in m.execute("SELECT gid FROM games")}
gids = [f"00224{n:05d}" for n in range(1, 1231)]
def one(g):
    try:
        return g, R._get(f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{g}.json")["game"]
    except Exception as e:
        return g, None
def mins(s):
    x = re.match(r"PT(\d+)M([\d.]+)S", s or "")
    return int(x.group(1)) + float(x.group(2)) / 60 if x else 0.0
t = time.time(); bad = []
with ThreadPoolExecutor(4) as ex:
    for g, b in ex.map(one, [g for g in gids if g not in have]):
        if not b:
            bad.append(g); continue
        h, a = b["homeTeam"], b["awayTeam"]
        m.execute("INSERT OR REPLACE INTO games VALUES (?,?,?,?,?,?,?,?)", (g, "2024-25", b["gameEt"][:10], h["teamTricode"], a["teamTricode"],
                  f'{h["teamCity"]} {h["teamName"]}', f'{a["teamCity"]} {a["teamName"]}', h["score"]))
        for side in (h, a):
            for p in side["players"]:
                s = p.get("statistics", {})
                m.execute("INSERT OR REPLACE INTO player_games VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                          (g, p["personId"], side["teamTricode"], 1 if p.get("starter") == "1" else 0, p.get("position") or "",
                           p["name"], mins(s.get("minutes")), s.get("points"), s.get("reboundsTotal"), s.get("assists"),
                           s.get("threePointersMade"), s.get("fieldGoalsAttempted")))
m.commit()
print("box", m.execute("SELECT COUNT(*) FROM games").fetchone(), "missing", len(bad), bad[:5], f"{time.time() - t:.0f}s", flush=True)
con = O.connect("onoff_2024.sqlite")
t = time.time()
print("lineups", O.fetch(con, m, "2024-25", workers=4, today="2026-11-06"), f"{time.time() - t:.0f}s", flush=True)
print(con.execute("SELECT COUNT(*), SUM(ok) FROM games").fetchone(), flush=True)
