"""DiLeo reached the projection log and the CLV shadow but not the firm ledger. Find the exact gate.

Both players are POR beneficiaries of the same out_player (Sarah Ashlee Barker), so team, opponent,
slate and injury are all held constant — whatever separates them is a per-player gate, which makes
this a clean comparison rather than a guess.

Also worth resolving: Carleton's d_stat is -1.3 (she scores FEWER points in the elevated sample)
while elev_avg 16.1 > season_avg 13.7. Those cannot both be increases over the same baseline, so
one of them is not what its name suggests — and if the projection leans on the flattering one, the
over is built on the wrong number.
"""
import sqlite3

DATE = "2026-07-31"

print("=== full projection rows, both players, same slate + same out_player ===")
con = sqlite3.connect("wnba_proj_log.sqlite")
con.row_factory = sqlite3.Row
cols = [d[1] for d in con.execute("PRAGMA table_info(projections)")]
print("  cols:", cols)
rows = {}
for who in ("Carleton", "DiLeo"):
    rs = con.execute("SELECT * FROM projections WHERE date=? AND player LIKE ?",
                     (DATE, "%" + who + "%")).fetchall()
    rows[who] = [dict(r) for r in rs]
    print("\n  --- %s: %d projection row(s)" % (who, len(rs)))
    for d in rows[who]:
        for k in cols:
            if d.get(k) not in (None, ""):
                print("      %-14s %s" % (k, d[k]))
        print("      " + "-" * 40)
con.close()

print("\n=== side-by-side on the fields the gates read ===")
KEYS = ("stat", "line", "odds", "ev", "d_min", "d_stat", "proj_hit", "proj_min", "n_elev",
        "elev_avg", "season_avg", "confidence", "pi_role", "vac", "driver", "samples", "stale")
print("  %-14s %-28s %-28s" % ("field", "Carleton", "DiLeo"))
for k in KEYS:
    c = rows["Carleton"][0].get(k) if rows["Carleton"] else "(no row)"
    d = rows["DiLeo"][0].get(k) if rows["DiLeo"] else "(no row)"
    mark = "   <-- differs" if str(c) != str(d) else ""
    print("  %-14s %-28s %-28s%s" % (k, str(c)[:28], str(d)[:28], mark))

print("\n=== what the CLV shadow recorded for each (it took BOTH) ===")
con = sqlite3.connect("wnba_clv.sqlite")
con.row_factory = sqlite3.Row
cc = [d[1] for d in con.execute("PRAGMA table_info(clv)")]
for who in ("Carleton", "DiLeo"):
    for r in con.execute("SELECT * FROM clv WHERE date=? AND player LIKE ?",
                         (DATE, "%" + who + "%")):
        d = dict(r)
        print("  %-10s %-10s %s" % (who, d.get("stat"),
                                    {k: v for k, v in d.items()
                                     if k in ("line", "odds", "ev", "tier", "bettable",
                                              "confidence", "d_min", "reason", "skip")}))
con.close()

print("\n=== the gates, as deployed ===")
import wnba_alert as WA
src = open("wnba_alert.py").read()
for name in ("BET_ROLES", "DEPTH_CAP", "EV_CAP", "EV_MAX"):
    if hasattr(WA, name):
        print("  wnba_alert.%-10s = %r" % (name, getattr(WA, name)))
print("\n  -- every place a row can be dropped between projection and ledger --")
import re
for m in re.finditer(r"^\s*(if|elif).*(continue|skip|drop|bettable|role_ok|ev\s*[<>]|EV_CAP).*$",
                     src, re.M):
    ln = src[:m.start()].count("\n") + 1
    print("    %4d  %s" % (ln, m.group(0).strip()[:110]))
