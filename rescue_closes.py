"""RESCUE pre-tee closes out of the 2-day rolling buffer into the durable store, before the prune.

WHY THIS IS URGENT. `golf_lines` keeps 2 days. St Jude teed off 2026-08-13T12:10 and finishes
Sunday 08-16, so its pre-tee prices are pruned ~08-15 — BEFORE the results they must be paired
against exist. That is precisely the failure that made the G2 matchup gate structurally unreachable
for an entire season, and until today it was ALSO silently eating every top-N close, because
`pga_tee_gate` could not resolve the bare market names ("Top 10", "Win Only") and so `golf_moves`
never advanced `pre_*` for them. The gate is fixed; this recovers what is still in the buffer.

WHAT A CLOSE IS HERE: the last price strictly BEFORE that market's own resolved deadline. Same
definition the rest of the system uses, via the same shared resolver — never a second copy.
Markets whose deadline will not resolve are SKIPPED and counted, never guessed.

WRITE-ONCE: only fills rows where close_ts IS NULL. An existing close is never overwritten.
"""
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import pga_tee_gate as TG

HERE = Path(__file__).resolve().parent
LINES, MOVES = HERE / "golf_lines.sqlite", HERE / "golf_moves.sqlite"
NO_HCAP = -9999.0

lc = sqlite3.connect(f"file:{LINES}?mode=ro", uri=True, timeout=90)
rows = lc.execute(
    "SELECT event, market, mtype, runner, COALESCE(handicap, ?) hc, collected_at, MIN(odds) "
    "FROM golf_lines WHERE odds > 1.0 "
    "GROUP BY event, market, runner, hc, collected_at", (NO_HCAP,)).fetchall()
lc.close()
print("buffer rows (deduped per timestamp): %d" % len(rows))

series = defaultdict(list)
meta = {}
for ev, mkt, mt, run, hc, ts, od in rows:
    k = (ev, mkt, run, hc)
    series[k].append((str(ts), float(od)))
    meta[k] = mt
print("distinct (event, market, runner, hcap) series: %d" % len(series))

cache = {}


def dl(ev, mkt):
    k = (ev, mkt)
    if k not in cache:
        try:
            d, why = TG.deadline(ev, mkt)
            cache[k] = (d.replace(microsecond=0).isoformat() if d else None, why)
        except Exception as e:                                             # noqa: BLE001
            cache[k] = (None, "resolver error: %s" % str(e)[:40])
    return cache[k]


mc = sqlite3.connect(str(MOVES), timeout=90)
mc.execute("PRAGMA busy_timeout=90000")
have = {(r[0], r[1], r[2], r[3]): r[4] for r in
        mc.execute("SELECT event, market, runner, hcap, close_ts FROM moves")}

ins = upd = skip_nodl = skip_nopre = skip_closed = 0
byfam = defaultdict(int)
for k, pts in series.items():
    ev, mkt, run, hc = k
    d, why = dl(ev, mkt)
    if not d:
        skip_nodl += 1
        continue
    pre = sorted([p for p in pts if p[0] < d])
    if not pre:
        skip_nopre += 1
        continue
    c_ts, c_od = pre[-1]
    o_ts, o_od = pre[0]
    allod = [p[1] for p in pts]
    if k in have:
        if have[k]:
            skip_closed += 1
            continue
        mc.execute("UPDATE moves SET tee_utc=COALESCE(tee_utc,?), tee_why=COALESCE(tee_why,?), "
                   "pre_ts=?, pre_odds=?, close_ts=?, close_odds=?, n_pre=? "
                   "WHERE event=? AND market=? AND runner=? AND hcap=? AND close_ts IS NULL",
                   (d, why, c_ts, c_od, c_ts, c_od, len(pre), ev, mkt, run, hc))
        upd += 1
    else:
        mc.execute(
            "INSERT OR IGNORE INTO moves(event,market,mtype,runner,hcap,rnd,tee_utc,tee_why,"
            "open_ts,open_odds,pre_ts,pre_odds,close_ts,close_odds,last_ts,last_odds,"
            "min_odds,max_odds,n_obs,n_pre) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ev, mkt, meta.get(k), run, hc, None, d, why, o_ts, o_od, c_ts, c_od, c_ts, c_od,
             sorted(pts)[-1][0], sorted(pts)[-1][1], min(allod), max(allod), len(pts), len(pre)))
        ins += 1
    byfam[mkt] += 1
mc.commit()

print("\ninserted %d · filled %d · skipped: no deadline %d, no pre-tee price %d, already closed %d"
      % (ins, upd, skip_nodl, skip_nopre, skip_closed))
print("\nrescued closes by market (top 14):")
for mk, n in sorted(byfam.items(), key=lambda x: -x[1])[:14]:
    print("   %-34s %d" % (mk[:34], n))

print("\n=== St Jude top-N now in the durable store ===")
for mk, n, cl in mc.execute(
        "SELECT market, COUNT(*), SUM(close_odds IS NOT NULL) FROM moves "
        "WHERE event LIKE ? AND market IN (?,?,?,?) GROUP BY 1",
        ("%St Jude%", "Top 5", "Top 10", "Top 20", "Win Only")):
    print("   %-10s n=%3d closed=%s" % (mk, n, cl))
for r in mc.execute("SELECT runner, close_odds, close_ts FROM moves WHERE event LIKE ? "
                    "AND market=? AND close_odds IS NOT NULL ORDER BY close_odds LIMIT 5",
                    ("%St Jude%", "Top 10")):
    print("     Top 10  %-22s %-8s @ %s" % (r[0][:22], r[1], str(r[2])[:16]))
mc.close()
