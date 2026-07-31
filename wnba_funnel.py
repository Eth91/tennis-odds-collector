"""Where did DiLeo get dropped, and how did Carleton survive?

Two separate questions and they must not be conflated:
  * DiLeo has NO ledger row, so she failed somewhere in the funnel BEFORE tiering. Walk the funnel
    in order — does she exist / is her team playing / are props posted / is there an injury that
    should elevate her / what is her role classification.
  * Carleton flagged at d_min=0.3 (no meaningful minutes bump) and ev=0.462, which is inside the
    documented fat-EV inversion (EV>=.20 hits WORSE than EV<.20) and above the EV cap of 0.25 that
    the 2026-07-17 calibration said was the only surviving fix. So how did she clear it?
"""
import glob
import json
import os
import sqlite3

MEN = ("DiLeo", "Dileo", "Di Leo")


def hits(db, who_list):
    """Every table/row in `db` naming any of who_list, whatever the player column is called."""
    if not os.path.exists(db):
        return
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        tc = [d[1] for d in con.execute("PRAGMA table_info(%s)" % t)]
        pc = [c for c in tc if c.lower() in
              ("player", "name", "player_name", "out_player", "participant")]
        if not pc:
            continue
        for c in pc:
            for who in who_list:
                try:
                    rs = con.execute("SELECT * FROM %s WHERE %s LIKE ? LIMIT 6" % (t, c),
                                     ("%" + who + "%",)).fetchall()
                except sqlite3.Error:
                    continue
                for r in rs:
                    d = dict(r)
                    small = {k: v for k, v in d.items() if v not in (None, "", 0)
                             and k in ("player", "name", "player_name", "out_player", "team",
                                       "stat", "line", "odds", "date", "game_date", "pred_date",
                                       "min", "minutes", "pts", "status", "role", "pi_role",
                                       "starter", "gs")}
                    print("    %-22s %-14s %s" % (os.path.basename(db), t, small or d))
    con.close()


print("=== 1. does DiLeo exist in ANY store? ===")
for db in sorted(glob.glob("*.sqlite")):
    if not any(k in db for k in ("wnba", "fanduel", "odds")):
        continue
    hits(db, MEN)
print("  (nothing above = she is not in the data at all)")

print("\n=== 2. tonight's slate + injuries ===")
for f in ("wnba_injury_report_cache.json", "wnba_board.json", "wnba_today.json"):
    if os.path.exists(f):
        try:
            d = json.load(open(f))
        except (ValueError, OSError):
            continue
        s = json.dumps(d)
        print("  %-34s %d bytes  DiLeo mentioned: %s  Carleton: %s"
              % (f, len(s), any(m in s for m in MEN), "Carleton" in s))

print("\n=== 3. Carleton's row in full (how did she clear the EV cap?) ===")
con = sqlite3.connect("wnba_ledger.sqlite")
con.row_factory = sqlite3.Row
for r in con.execute("SELECT * FROM predictions WHERE player LIKE '%Carleton%' "
                     "AND pred_date=(SELECT MAX(pred_date) FROM predictions)"):
    d = dict(r)
    for k in ("pred_date", "out_player", "player", "team", "opp", "stat", "line", "odds",
              "proj_hit", "season_avg", "elev_avg", "proj_min", "n_elev", "ev", "d_stat",
              "d_min", "driver", "vac", "confidence", "pi_role", "tier", "side", "samples",
              "basis", "stale", "regime", "spread"):
        print("    %-12s %s" % (k, d.get(k)))
    print("    " + "-" * 50)

print("\n=== 4. what the EV cap and role gate actually are, as deployed ===")
import wnba_alert as WA
for name in ("EV_CAP", "EV_MAX", "MAX_EV", "BET_ROLES", "DEPTH_CAP", "ROLE_OK"):
    if hasattr(WA, name):
        print("    wnba_alert.%-12s = %r" % (name, getattr(WA, name)))
import wnba_slip as WS
for name in ("EV_CAP", "EV_MAX", "MAX_EV", "SWAP_MARGIN"):
    if hasattr(WS, name):
        print("    wnba_slip.%-13s = %r" % (name, getattr(WS, name)))
con.close()
