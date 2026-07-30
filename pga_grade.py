"""⛳ Grade the E1 paper flags off ESPN round scores + enforce the pre-launch tripwire.

GRADING RULES (v1, deliberately conservative — a paper meter must never award itself wins
on judgment calls):
  72-hole matchbet   graded only when BOTH players show 4 completed rounds (winner = lower
                     total) OR both show exactly 2 with the event past the cut (both missed:
                     lower 36-hole total). One side WD/short -> VOID. FD's actual rules are
                     more generous, so v1 under-grades rather than mis-grades.
  round-N matchbet   graded when both have that round's score.
  ties -> push (pnl 0).

TRIPWIRE (PGA_PLAN law 7, defined BEFORE launch): after 25 graded, bench the stream when
break-even can be STATISTICALLY RULED OUT — the observed win rate more than 2 standard
errors below the implied breakeven. (v1 said "below 52% of the breakeven pace" but the code
fired at 1.04x breakeven, a 4x discrepancy, and that threshold sits ABOVE breakeven so it
benched an exactly-break-even stream 58% of the time at n=25 and 85% at n=600.) No
auto-ntfy — the nightly digest and the board carry it; this stream never had ping rights.
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
                # WD RULE (2026-07-29): FanDuel voids a matchup only if a player never
                # STARTS. Once both have a round on the board, a mid-event WD loses to the
                # completer. v1 voided all of these, which quietly under-counted real
                # losses and flattered the paper record.
                if len(rs) >= 1 and len(os_) >= 4:
                    res = "L"
                elif len(os_) >= 1 and len(rs) >= 4:
                    res = "W"
                else:
                    res = "V"
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
        # PROPER ONE-SIDED TEST (2026-07-30). The old rule fired below 0.52*be*2 = 1.04*be —
        # a threshold ABOVE breakeven, so it was not testing "is this broken" but "is this
        # comfortably profitable", and it benched a stream that was EXACTLY break-even 58% of
        # the time at n=25 rising to 85% at n=600. It also contradicted its own docstring
        # ("52% of the breakeven pace" = 0.52*be), a 4x discrepancy. Now: bench only when the
        # observed rate is more than 2 standard errors BELOW breakeven, i.e. break-even can
        # be statistically ruled out. That holds the false-bench rate near 2% at every n.
        se = (be * (1 - be) / n) ** 0.5
        z = (w / n - be) / se if se > 0 else 0.0
        if z <= -2.0:
            print(f"🚨 E1 TRIPWIRE: {w}-{l} ({100*w/n:.0f}%) vs breakeven {100*be:.0f}% "
                  f"after {n} graded, z={z:+.2f} — break-even RULED OUT, BENCH this stream "
                  f"(PGA_PLAN law 7)")
        elif w / n < be:
            print(f"   E1 below breakeven ({100*w/n:.0f}% vs {100*be:.0f}%, z={z:+.2f}) but "
                  f"not yet distinguishable from noise at n={n} — keep collecting")
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
