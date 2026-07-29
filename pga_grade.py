"""⛳ Grade the E1 paper flags off ESPN round scores + enforce the pre-launch tripwire.

GRADING RULES (v1, deliberately conservative — a paper meter must never award itself wins
on judgment calls):
  72-hole matchbet   graded only when BOTH players show 4 completed rounds (winner = lower
                     total) OR both show exactly 2 with the event past the cut (both missed:
                     lower 36-hole total). One side WD/short -> VOID. FD's actual rules are
                     more generous, so v1 under-grades rather than mis-grades.
  round-N matchbet   graded when both have that round's score.
  ties -> push (pnl 0).

TRIPWIRE (PGA_PLAN law 7, defined BEFORE launch): after 25 graded, if the win rate is
below 52% of the implied-breakeven pace, print the BENCH alarm loudly. No auto-ntfy —
the nightly digest and the board carry it; this stream never had ping rights to lose.
"""
import datetime as dt
import re
import sqlite3
from pathlib import Path

import pga_field as F
import pga_e1 as E1

HERE = Path(__file__).resolve().parent
PAPER = HERE / "pga_paper.sqlite"


def main():
    ev = F.event()
    name = ev.get("name") or ""
    state, desc = F.status(ev)
    scores = F.round_scores(ev)
    sn = {E1.norm(k): v for k, v in scores.items()}
    cut_done = any(len(v) >= 3 for v in scores.values())

    con = sqlite3.connect(PAPER)
    con.execute(E1.DDL)
    graded = 0
    for key, mkt, runner, opp, odds in con.execute(
            "SELECT key, market, runner, opp, odds FROM flags WHERE result IS NULL").fetchall():
        rs, os_ = sn.get(E1.norm(runner)), sn.get(E1.norm(opp))
        if rs is None or os_ is None:
            continue
        m = re.search(r"Round (\d)|(\d)(?:st|nd|rd|th) Round", mkt)
        res = None
        if m:                                             # single-round matchbet
            rn = int(m.group(1) or m.group(2))
            if len(rs) >= rn and len(os_) >= rn:
                a, b = rs[rn - 1], os_[rn - 1]
                res = "W" if a < b else ("L" if a > b else "P")
        else:                                             # 72-hole matchbet
            if len(rs) >= 4 and len(os_) >= 4:
                a, b = sum(rs[:4]), sum(os_[:4])
                res = "W" if a < b else ("L" if a > b else "P")
            elif state == "post" and cut_done and len(rs) == 2 and len(os_) == 2:
                a, b = sum(rs), sum(os_)                  # both missed the cut
                res = "W" if a < b else ("L" if a > b else "P")
            elif state == "post":
                res = "V"                                 # WD/short data -> void, honestly
        if res is None:
            continue
        pnl = (odds - 1) if res == "W" else (-1.0 if res == "L" else 0.0)
        con.execute("UPDATE flags SET result=?, pnl=?, graded_at=? WHERE key=?",
                    (res, pnl, dt.datetime.utcnow().replace(microsecond=0).isoformat(), key))
        graded += 1
    con.commit()

    w, l = [con.execute("SELECT COUNT(*) FROM flags WHERE result=?", (x,)).fetchone()[0]
            for x in ("W", "L")]
    units = con.execute("SELECT COALESCE(SUM(pnl),0) FROM flags").fetchone()[0]
    avg_odds = con.execute("SELECT AVG(odds) FROM flags WHERE result IN ('W','L')"
                           ).fetchone()[0] or 1.91
    con.close()
    print(f"pga grade: +{graded} newly graded — E1 record {w}-{l}  {units:+.2f}u")
    n = w + l
    if n >= 25:
        be = 1 / avg_odds
        if (w / n) < 0.52 * be * 2:                       # <52% of breakeven pace
            print(f"🚨 E1 TRIPWIRE: {w}-{l} ({100*w/n:.0f}%) vs breakeven {100*be:.0f}% "
                  f"after {n} graded — BENCH this stream (PGA_PLAN law 7)")
    # PRESERVE THE E3 BLOCK (2026-07-29): _write_board rebuilds pga_board.json from
    # scratch, and grading runs AFTER pga_e3 in the cron — so it was wiping the E3
    # preview every pass. The board showed 0 rows while e3 had just produced 15.
    try:
        import json as _j
        _prev = _j.loads(E1.BOARD.read_text()).get("e3")
    except Exception:
        _prev = None
    E1._write_board(name)
    if _prev:
        try:
            import json as _j
            _b = _j.loads(E1.BOARD.read_text())
            _b["e3"] = _prev
            _t = E1.BOARD.with_suffix(".tmp")
            _t.write_text(_j.dumps(_b))
            _t.replace(E1.BOARD)
        except Exception:
            pass


if __name__ == "__main__":
    main()
