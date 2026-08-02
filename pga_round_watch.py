"""Wait for a round to finish, harvest it, then run the learning engine. Nothing else.

COMPLETION TEST, and the trap it avoids. The R1 watcher tested `holes < 18` and burned a three-hour
deadline, because a player who never teed off has 0 holes and never reaches 18 — the loop could not
terminate. So completion is judged on the players who ACTUALLY STARTED, and there are three
independent ways out so a single stalled feed cannot hang it:

  1. >= DONE_FRAC of the starters have a completed round;
  2. the completed count stops moving for STALL_POLLS consecutive polls (a WD or two will never
     finish, so "no longer changing" is the honest end of a round);
  3. a hard wall-clock deadline.

Whichever fires first, it harvests the event and runs pga_learn.py. It never prices, never bets,
never touches the frozen model.

    python3 pga_round_watch.py <tid> <round> [--now]
"""
import datetime as dt
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLL_S = 600            # 10 minutes; a round does not end faster than that
DONE_FRAC = 0.90        # of the players who actually teed off
STALL_POLLS = 3         # unchanged for this many polls = the round is over
MAX_HOURS = 8.0


def _log(msg):
    print("%s  %s" % (dt.datetime.utcnow().strftime("%H:%M:%SZ"), msg), flush=True)


def starters(tid, rnd):
    """How many players were on the tee sheet for this round — the honest denominator."""
    import sqlite3
    try:
        c = sqlite3.connect(str(HERE / "pga_tees.sqlite"))
        n = c.execute("SELECT COUNT(*) FROM tee_sheet WHERE tid=? AND rnd=? AND tee_ms IS NOT NULL",
                      (str(tid), int(rnd))).fetchone()[0]
        c.close()
        return n
    except Exception:                                              # noqa: BLE001
        return 0


def completed(tid, tname, rnd):
    """Players with a COMPLETED round `rnd`, straight from the scorecards.

    scorecard_rows already refuses anything under 15 holes, so a player mid-round or withdrawn is
    simply absent rather than counted as a zero."""
    import pga_birdies as B
    n = 0
    try:
        for pid, pname in B.players_of(tid):
            try:
                for row in B.scorecard_rows(tid, tname, pid, pname):
                    if int(row[3] or 0) == int(rnd):
                        n += 1
                        break
            except Exception:                                      # noqa: BLE001
                continue
    except Exception as e:                                         # noqa: BLE001
        _log("scorecard poll failed: %s" % str(e)[:70])
    return n


def run(cmd):
    _log("$ %s" % " ".join(cmd))
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True, timeout=1800)
    out = (p.stdout or "") + (p.stderr or "")
    for line in out.strip().splitlines()[-25:]:
        print("    " + line, flush=True)
    return p.returncode


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    tid, rnd = sys.argv[1], int(sys.argv[2])
    import pga_birdies as B
    tname = None
    try:
        import sqlite3
        c = sqlite3.connect(str(HERE / "pga_tees.sqlite"))
        r = c.execute("SELECT tname FROM tee_sheet WHERE tid=? LIMIT 1", (tid,)).fetchone()
        c.close()
        tname = r[0] if r else tid
    except Exception:                                              # noqa: BLE001
        tname = tid
    tee_n = starters(tid, rnd)
    _log("watching %s (%s) round %d — %d starters on the tee sheet" % (tname, tid, rnd, tee_n))

    if "--now" not in sys.argv:
        t0 = time.time()
        last, stall = -1, 0
        while True:
            n = completed(tid, tname, rnd)
            frac = (n / tee_n) if tee_n else 0.0
            _log("completed R%d: %d/%d (%.0f%%)" % (rnd, n, tee_n, 100 * frac))
            if tee_n and frac >= DONE_FRAC:
                _log("round complete (%.0f%% of starters finished)" % (100 * frac))
                break
            stall = stall + 1 if n == last else 0
            last = n
            if stall >= STALL_POLLS and n > 0 and (not tee_n or frac > 0.5):
                _log("count unchanged for %d polls at %d — treating the round as over" % (stall, n))
                break
            if (time.time() - t0) / 3600.0 > MAX_HOURS:
                _log("hard deadline reached; proceeding with what has settled")
                break
            time.sleep(POLL_S)

    _log("harvesting the event so the round enters birdie_rounds")
    run([sys.executable, "-c",
         "import pga_birdies as B; print(B.harvest(years=(2026,)))"])
    _log("grading + evidence")
    run(["bash", "pga_after_event.sh"])
    _log("learning engine")
    run([sys.executable, "pga_learn.py", "--round"])
    _log("done — PGA_LEARN.md and pga_evidence.md refreshed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
