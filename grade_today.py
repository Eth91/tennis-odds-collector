#!/usr/bin/env python3
"""Grade today's already-started picks using in-play price collapse. 1u = $100.

Official results post tomorrow and ESPN's scoreboard is 403 from this box, so the evidence
available is our own price history. Both books bank quotes every 15-30 minutes INCLUDING in-play,
and a price that collapses toward 1.0 is a winner while one that blows out is a loser.

CONFIDENCE IS EXPLICIT, because an inference is not a result:
    DECIDED   a side's last quote is <= 1.10, or the opponent's is >= 8.0  -> effectively settled
    LEANING   moved decisively (>35%) but not to an extreme                -> in progress
    UNKNOWN   too few in-play quotes to say                                -> not graded

Only DECIDED rows are counted in the P&L. The stake is 1u = $100 at the PRE-MATCH price logged in
the ledger, never the in-play price - that distinction is the bug this exercise already caught.
"""
import datetime as dt
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = 100.0
now = dt.datetime.utcnow().isoformat()
lg = sqlite3.connect("file:%s?mode=ro" % (HERE / "ml_ledger.sqlite"), uri=True)
fd = sqlite3.connect("file:%s?mode=ro" % (HERE / "tennis_fd.sqlite"), uri=True)

bets = lg.execute("SELECT start_time,event,pick,opp,odds,edge,tour FROM bets "
                  "WHERE start_time < ? ORDER BY start_time", (now,)).fetchall()
print("picks already started: %d   (stake 1u = $%.0f at the PRE-MATCH price)\n" % (len(bets), UNIT))
print("%-11s %-32s %-18s %5s %8s  %-9s %s"
      % ("start", "match", "pick", "odds", "edge", "verdict", "last quotes (pick / opp)"))
print("-" * 120)

dec_w = dec_l = 0
pnl = 0.0
lean_w = lean_l = 0
unknown = 0
for stt, ev, pk, opp, od, eg, tour in bets:
    def series(name):
        r = fd.execute("""SELECT odds, collected_at FROM fd_tennis
                          WHERE event_name=? AND runner_name=? AND market_type='MATCH_BETTING'
                          ORDER BY collected_at""", (ev, name)).fetchall()
        return r
    sp, so = series(pk), series(opp)
    if not sp:
        # runner_name may carry extra text; fall back to a surname match
        cand = fd.execute("""SELECT runner_name FROM fd_tennis WHERE event_name=?
                             AND market_type='MATCH_BETTING' GROUP BY runner_name""",
                          (ev,)).fetchall()
        for (rn,) in cand:
            if pk.split()[-1].lower() in rn.lower():
                sp = series(rn)
            elif opp.split()[-1].lower() in rn.lower():
                so = series(rn)
    lp = sp[-1][0] if sp else None
    lo = so[-1][0] if so else None
    inplay = [x for x in (sp or []) if x[1] > stt]
    verdict = "UNKNOWN"
    if lp is not None and lo is not None and len(inplay) >= 1:
        if lp <= 1.10 or lo >= 8.0:
            verdict = "WON"
        elif lo <= 1.10 or lp >= 8.0:
            verdict = "LOST"
        elif sp and lp < sp[0][0] * 0.65:
            verdict = "leaning W"
        elif sp and lp > sp[0][0] * 1.35:
            verdict = "leaning L"
    if verdict == "WON":
        dec_w += 1
        pnl += (od - 1.0) * UNIT
    elif verdict == "LOST":
        dec_l += 1
        pnl -= UNIT
    elif verdict == "leaning W":
        lean_w += 1
    elif verdict == "leaning L":
        lean_l += 1
    else:
        unknown += 1
    print("%-11s %-32s %-18s %5.2f %+8.3f  %-9s  %s / %s  (%d in-play)"
          % (str(stt)[5:16], str(ev)[:32], str(pk)[:18], od, eg, verdict,
             ("%.2f" % lp) if lp else "-", ("%.2f" % lo) if lo else "-", len(inplay)))

print()
print("=" * 96)
print("SETTLED-BY-PRICE RESULT   (only DECIDED rows counted)")
print("=" * 96)
n = dec_w + dec_l
if n:
    print("   record %d-%d  |  P&L %+.0f  |  ROI %+.1f%%  on %d bets at $%.0f each"
          % (dec_w, dec_l, pnl, 100.0 * pnl / (n * UNIT), n, UNIT))
else:
    print("   nothing decided yet")
print("   still in progress: %d leaning our way, %d against, %d unknown"
      % (lean_w, lean_l, unknown))
print()
print("   ⚠️ Inferred from price collapse, not official results. The ledger itself settles from")
print("   results at 06:20 UTC and is the record that counts.")
