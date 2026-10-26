#!/usr/bin/env python3
"""Re-import TML with the FULL serve/return stat block, for a point-level model.

The first import kept only aces and service points, which is enough for an ace model and useless
for a match model. A serve/return model needs the points actually WON:

    1stIn / 1stWon / 2ndWon / svpt   -> serve points won, the quantity a match is built from
    bpSaved / bpFaced               -> clutch behaviour on break points
    the OPPONENT's mirror of those  -> return points won

From those two numbers - P(win a point on serve) for each player - a match probability follows
analytically through the standard game/set/match recursion, with NO ratings involved. That is a
genuinely different model from Elo, not a re-weighting of it: Elo compresses a career into one
number, while serve/return keeps the two halves of tennis separate and recombines them per matchup.
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
UA = {"User-Agent": "Mozilla/5.0"}

DDL = """
CREATE TABLE IF NOT EXISTS srv_pm(
  date TEXT, year INT, tourney TEXT, level TEXT, surface TEXT, best_of INT, round TEXT,
  player TEXT, opp TEXT, won INT,
  svpt INT, first_in INT, first_won INT, second_won INT, sv_gms INT, bp_saved INT, bp_faced INT,
  o_svpt INT, o_first_in INT, o_first_won INT, o_second_won INT, o_sv_gms INT,
  o_bp_saved INT, o_bp_faced INT,
  PRIMARY KEY (date, tourney, player, opp)
);
CREATE INDEX IF NOT EXISTS ix_srv_pl ON srv_pm(player, date);
CREATE INDEX IF NOT EXISTS ix_srv_yr ON srv_pm(year);
"""


def n(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


con = sqlite3.connect(str(DB), timeout=60)
con.execute("PRAGMA busy_timeout=60000")
con.executescript(DDL)
con.commit()
tot = 0
for y in range(2015, 2027):
    try:
        req = urllib.request.Request(BASE % y, headers=UA)
        raw = urllib.request.urlopen(req, timeout=90).read().decode("utf8", "ignore")
    except Exception as e:                                              # noqa: BLE001
        print("   %d FETCH FAILED %s" % (y, str(e)[:40]))
        continue
    rd = csv.DictReader(io.StringIO(raw))
    batch = []
    for r in rd:
        d = str(r.get("tourney_date") or "")
        if len(d) != 8:
            continue
        date = "%s-%s-%s" % (d[:4], d[4:6], d[6:])
        bo = n(r.get("best_of")) or 3
        for side, other in (("w", "l"), ("l", "w")):
            sv = n(r.get("%s_svpt" % side))
            if not sv:
                continue
            batch.append((
                date, y, r.get("tourney_name"), r.get("tourney_level"), r.get("surface"),
                bo, r.get("round"),
                r.get("winner_name") if side == "w" else r.get("loser_name"),
                r.get("loser_name") if side == "w" else r.get("winner_name"),
                1 if side == "w" else 0,
                sv, n(r.get("%s_1stIn" % side)), n(r.get("%s_1stWon" % side)),
                n(r.get("%s_2ndWon" % side)), n(r.get("%s_SvGms" % side)),
                n(r.get("%s_bpSaved" % side)), n(r.get("%s_bpFaced" % side)),
                n(r.get("%s_svpt" % other)), n(r.get("%s_1stIn" % other)),
                n(r.get("%s_1stWon" % other)), n(r.get("%s_2ndWon" % other)),
                n(r.get("%s_SvGms" % other)), n(r.get("%s_bpSaved" % other)),
                n(r.get("%s_bpFaced" % other))))
    if batch:
        con.executemany("INSERT OR IGNORE INTO srv_pm VALUES(%s)" % ",".join(["?"] * 24), batch)
        con.commit()
        tot += len(batch)
    print("   %d  %d rows" % (y, len(batch)))

rows = con.execute("""SELECT COUNT(*), COUNT(DISTINCT player), MIN(date), MAX(date) FROM srv_pm
                      WHERE first_won IS NOT NULL""").fetchone()
print("\nsrv_pm: %d rows with full serve stats | %d players | %s .. %s" % rows)
print("\nserve-points-won rate by surface (the model's core quantity):")
for s, c, spw in con.execute("""SELECT surface, COUNT(*),
                                AVG(1.0*(first_won+second_won)/svpt) FROM srv_pm
                                WHERE first_won IS NOT NULL AND svpt>0 AND surface!=''
                                GROUP BY surface ORDER BY 2 DESC"""):
    print("   %-8s n=%6d  P(win point on serve) = %.4f" % (s, c, spw))
con.close()
