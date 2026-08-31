#!/usr/bin/env python3
"""Build the ace dataset from TML-Database. One row per PLAYER-MATCH, not per match.

Aces are a SERVER quantity, so the unit has to be the player-match: the same match contributes two
rows, one per player, each with that player's aces, their own service workload, and the opponent
they were serving against. Storing it match-wise (w_ace / l_ace) would make every downstream join
re-derive that and get the opponent side wrong half the time.

WHAT DRIVES AN ACE COUNT, and why each field is kept:
  serve quality   the player's own ace rate - by far the most stable tennis stat
  return quality  the OPPONENT's ace-conceded rate; some returners are far harder to ace
  surface         grass rewards the serve, clay suppresses it
  indoor          no wind, no sun - measurably faster conditions
  WORKLOAD        aces scale with how many service points you actually play. A three-set blowout
                  and a five-set war are different opportunities for the same server, so any model
                  that predicts a COUNT without conditioning on workload is really predicting
                  match length in disguise.
  best_of         3 vs 5 is the single largest workload driver.

TML is ATP-only. WTA ace history is a known gap in this project and is recorded as such rather
than silently omitted - the FanDuel collector banks WTA ace ladders either way, so the WTA model
is blocked on data, not on method.
"""
import csv
import io
import sqlite3
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "tennis_ace.sqlite"
BASE = "https://raw.githubusercontent.com/Tennismylife/TML-Database/master/%d.csv"
YEARS = list(range(2015, 2027))
UA = {"User-Agent": "Mozilla/5.0"}

DDL = """
CREATE TABLE IF NOT EXISTS ace_pm(
  date TEXT, year INT, tourney TEXT, level TEXT, surface TEXT, indoor TEXT,
  best_of INT, round TEXT,
  player TEXT, player_id TEXT, player_hand TEXT, player_ht REAL, player_rank REAL,
  opp TEXT, opp_id TEXT, opp_hand TEXT, opp_ht REAL, opp_rank REAL,
  won INT, aces INT, dfs INT, svpt INT, sv_gms INT, first_in INT, minutes REAL,
  PRIMARY KEY (date, tourney, player, opp)
);
CREATE INDEX IF NOT EXISTS ix_ace_pl ON ace_pm(player, date);
CREATE INDEX IF NOT EXISTS ix_ace_op ON ace_pm(opp, date);
CREATE INDEX IF NOT EXISTS ix_ace_yr ON ace_pm(year);
"""


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    con = sqlite3.connect(str(DB), timeout=60)
    con.execute("PRAGMA busy_timeout=60000")
    try:
        con.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        pass
    con.executescript(DDL)
    con.commit()
    total = 0
    for y in YEARS:
        try:
            req = urllib.request.Request(BASE % y, headers=UA)
            raw = urllib.request.urlopen(req, timeout=60).read().decode("utf8", "ignore")
        except Exception as e:                                          # noqa: BLE001
            print("   %d  FETCH FAILED %s" % (y, str(e)[:50]))
            continue
        rd = csv.DictReader(io.StringIO(raw))
        batch = []
        for r in rd:
            d = str(r.get("tourney_date") or "")
            if len(d) != 8:
                continue
            date = "%s-%s-%s" % (d[:4], d[4:6], d[6:])
            bo = num(r.get("best_of")) or 3
            for side, other in (("w", "l"), ("l", "w")):
                aces = num(r.get("%s_ace" % side))
                svpt = num(r.get("%s_svpt" % side))
                if aces is None or not svpt:
                    continue
                batch.append((
                    date, y, r.get("tourney_name"), r.get("tourney_level"), r.get("surface"),
                    r.get("indoor"), int(bo), r.get("round"),
                    r.get("%sinner_name" % ("w" if side == "w" else "")) if False else
                    r.get("winner_name") if side == "w" else r.get("loser_name"),
                    r.get("winner_id") if side == "w" else r.get("loser_id"),
                    r.get("winner_hand") if side == "w" else r.get("loser_hand"),
                    num(r.get("winner_ht") if side == "w" else r.get("loser_ht")),
                    num(r.get("winner_rank") if side == "w" else r.get("loser_rank")),
                    r.get("loser_name") if side == "w" else r.get("winner_name"),
                    r.get("loser_id") if side == "w" else r.get("winner_id"),
                    r.get("loser_hand") if side == "w" else r.get("winner_hand"),
                    num(r.get("loser_ht") if side == "w" else r.get("winner_ht")),
                    num(r.get("loser_rank") if side == "w" else r.get("winner_rank")),
                    1 if side == "w" else 0,
                    int(aces), int(num(r.get("%s_df" % side)) or 0), int(svpt),
                    int(num(r.get("%s_SvGms" % side)) or 0),
                    int(num(r.get("%s_1stIn" % side)) or 0),
                    num(r.get("minutes"))))
        if batch:
            con.executemany("INSERT OR IGNORE INTO ace_pm VALUES(%s)" % ",".join(["?"] * 25), batch)
            con.commit()
            total += len(batch)
        print("   %d  %d player-match rows" % (y, len(batch)))
    n, pl, mn, mx = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT player), MIN(date), MAX(date) FROM ace_pm").fetchone()
    print("\nTOTAL %d player-match rows | %d players | %s .. %s" % (n, pl, mn, mx))
    print("\naces per match by surface:")
    for s, c, a, sg in con.execute(
            "SELECT surface, COUNT(*), AVG(aces), AVG(sv_gms) FROM ace_pm GROUP BY surface "
            "ORDER BY COUNT(*) DESC"):
        print("   %-10s n=%6d  mean aces %5.2f  mean service games %5.1f" % (str(s), c, a or 0, sg or 0))
    print("\nby best_of:")
    for bo, c, a in con.execute("SELECT best_of, COUNT(*), AVG(aces) FROM ace_pm GROUP BY best_of"):
        print("   bo%s  n=%6d  mean aces %5.2f" % (bo, c, a or 0))
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
